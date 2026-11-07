"""FR-11: Веб-интерфейс monitoring_checker (Streamlit).

Запуск: streamlit run app.py
"""

import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml
from dotenv import load_dotenv

from analyzers.claude_analyzer import (
    AnalysisResult,
    analyze_document,
    extract_borrower_fields,
    parse_issues,
)
from external.cache import FileCache
from external.gis2 import check_address
from external.kgd import check_counterparty_bin
from loaders.dispatcher import load_document
from template.exporter import build_issues_df, build_summary_df, export_report
from template.normalizer import normalize_to_template

import anthropic

load_dotenv()

CONFIG_PATH = Path(__file__).parent / "config.yaml"
SEVERITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
VERDICT_LABELS = {
    "ok": "✅ Без замечаний",
    "issues": "⚠️ Есть замечания",
    "insufficient_data": "❔ Недостаточно данных",
}


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def process_file(uploaded_file, config: dict, client: anthropic.Anthropic | None, model: str,
                 bank_name: str, gis2_key: str | None, gis2_enabled: bool, kgd_enabled: bool,
                 cache: FileCache) -> AnalysisResult:
    """Полный цикл обработки одного файла: загрузка → поля → проверка → внешние проверки."""
    result = AnalysisResult()

    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        document = load_document(tmp_path, config)
    finally:
        os.unlink(tmp_path)

    if document.error:
        result.error = document.error
        return result
    if not document.text.strip():
        result.error = "Не удалось извлечь текст из файла"
        return result

    if client is None:
        result.error = "Не задан ключ Anthropic API"
        return result

    # FR-6: извлечение полей заемщика
    try:
        result.borrower_fields = extract_borrower_fields(client, document.text, model)
    except Exception as exc:
        result.error = f"Ошибка извлечения полей: {exc}"
        return result

    # FR-7: проверка отчета
    try:
        check = analyze_document(client, document.text, model=model)
        result.verdict = check.get("verdict", "insufficient_data")
        result.summary = check.get("summary", "")
        result.issues = parse_issues(check.get("issues", []))
    except Exception as exc:
        result.error = f"Ошибка анализа: {exc}"
        return result

    # FR-8: внешние проверки
    fields = result.borrower_fields

    if gis2_enabled and fields.get("project_address"):
        addr = check_address(fields["project_address"], gis2_key, cache)
        if addr.status == "ok":
            fields["project_address_normalized"] = addr.normalized_address
        elif addr.status == "not_found":
            from analyzers.claude_analyzer import Issue
            result.issues.append(Issue(
                severity="medium",
                check="внешняя проверка (2ГИС)",
                field="Адрес реализации проекта",
                description="Адрес не найден в 2ГИС",
                evidence=fields["project_address"],
            ))
            if result.verdict == "ok":
                result.verdict = "issues"

    if kgd_enabled:
        from analyzers.claude_analyzer import Issue
        if fields.get("bin_iin"):
            check_bin = check_counterparty_bin(fields["bin_iin"])
            if not check_bin.format_ok:
                result.issues.append(Issue(
                    severity="high",
                    check="внешняя проверка (КГД)",
                    field="БИН заемщика",
                    description=check_bin.message,
                    evidence=str(fields["bin_iin"]),
                ))
                if result.verdict == "ok":
                    result.verdict = "issues"
        for cp in fields.get("counterparties") or []:
            if not isinstance(cp, dict):
                continue
            check_cp = check_counterparty_bin(cp.get("bin"))
            if not check_cp.format_ok:
                result.issues.append(Issue(
                    severity="medium",
                    check="внешняя проверка (КГД)",
                    field="Контрагенты",
                    description=f"Контрагент «{cp.get('name') or '?'}»: {check_cp.message}",
                    evidence=str(cp.get("bin")),
                ))
                if result.verdict == "ok":
                    result.verdict = "issues"

    return result


def main() -> None:
    st.set_page_config(page_title="Проверка мониторинговых отчетов", layout="wide")
    st.title("Проверка мониторинговых отчетов банков")

    config = load_config()

    with st.sidebar:
        st.header("Настройки")
        api_key = st.text_input(
            "Ключ Anthropic API",
            value=os.getenv("ANTHROPIC_API_KEY", ""),
            type="password",
        )
        model = st.text_input("Модель", value=config.get("model", "claude-sonnet-4-5"))
        bank_name = st.text_input("Название банка", value="")
        st.subheader("Внешние проверки")
        ext_cfg = config.get("external_checks", {})
        gis2_enabled = st.checkbox("2ГИС (адреса)", value=ext_cfg.get("gis2_enabled", True))
        gis2_key = st.text_input(
            "Ключ 2ГИС", value=os.getenv("GIS2_API_KEY", ""), type="password",
            disabled=not gis2_enabled,
        )
        kgd_enabled = st.checkbox("КГД (формат БИН)", value=ext_cfg.get("kgd_enabled", True))

    uploaded_files = st.file_uploader(
        "Загрузите отчеты (xlsx, xls, xlsm, docx, pdf, jpg, jpeg, png)",
        type=["xlsx", "xls", "xlsm", "docx", "pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Загрузите один или несколько файлов для проверки.")
        return

    max_mb = config.get("max_file_size_mb", 50)
    oversized = [f.name for f in uploaded_files if f.size > max_mb * 1024 * 1024]
    if oversized:
        st.error(f"Файлы превышают {max_mb} МБ: {', '.join(oversized)}")

    if not st.button("Запустить проверку", type="primary"):
        return

    client = anthropic.Anthropic(api_key=api_key) if api_key else None
    if client is None:
        st.warning("Ключ Anthropic API не задан — анализ невозможен.")

    cache = FileCache(ttl_hours=config.get("cache_ttl_hours", 72))
    template_columns = config.get("template_columns", [])

    results: list[AnalysisResult] = []
    progress = st.progress(0, text="Обработка файлов...")

    for idx, uploaded_file in enumerate(uploaded_files):
        progress.progress(
            idx / len(uploaded_files),
            text=f"Обработка: {uploaded_file.name} ({idx + 1}/{len(uploaded_files)})",
        )
        if uploaded_file.name in oversized:
            results.append(AnalysisResult(error=f"Файл превышает {max_mb} МБ"))
            continue
        try:
            results.append(process_file(
                uploaded_file, config, client, model, bank_name,
                gis2_key if gis2_enabled else None, gis2_enabled, kgd_enabled, cache,
            ))
        except Exception as exc:
            results.append(AnalysisResult(error=str(exc)))

    progress.progress(1.0, text="Готово")

    # Итоги
    errors = [r for r in results if r.error]
    ok = [r for r in results if not r.error and r.verdict == "ok"]
    with_issues = [r for r in results if not r.error and r.verdict == "issues"]
    insufficient = [r for r in results if not r.error and r.verdict == "insufficient_data"]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Всего", len(results))
    col2.metric("Без замечаний", len(ok))
    col3.metric("С замечаниями", len(with_issues))
    col4.metric("Недостаточно данных", len(insufficient))
    col5.metric("Ошибки обработки", len(errors))

    # Таблица данных
    valid = [r for r in results if not r.error]
    if valid:
        data_df = normalize_to_template(
            [r.borrower_fields for r in valid],
            [bank_name] * len(valid),
            template_columns,
        )
        st.subheader("Данные")
        st.dataframe(data_df, use_container_width=True)

    # Замечания
    issues_per_record = []
    for i, r in enumerate(results):
        borrower = r.borrower_fields.get("borrower_name") or uploaded_files[i].name
        if r.issues:
            issues_per_record.append((i + 1, borrower, bank_name, r.issues))
    issues_df = build_issues_df(issues_per_record)

    if not issues_df.empty:
        st.subheader("Замечания")
        display_df = issues_df.copy()
        display_df["Критичность"] = display_df["Критичность"].map(
            lambda s: f"{SEVERITY_ICONS.get(s, '')} {s}"
        )
        st.dataframe(display_df, use_container_width=True)

    # Ошибки
    if errors:
        st.subheader("Ошибки обработки")
        for i, r in enumerate(results):
            if r.error:
                st.error(f"{uploaded_files[i].name}: {r.error}")

    # Скачивание итогового Excel
    summary_df = build_summary_df(
        total=len(results), ok=len(ok), issues=len(with_issues),
        insufficient=len(insufficient),
        extra_rows=[("Ошибки обработки", len(errors))] if errors else None,
    )
    data_df = normalize_to_template(
        [r.borrower_fields for r in valid],
        [bank_name] * len(valid),
        template_columns,
    ) if valid else pd.DataFrame(columns=template_columns)

    report_bytes = export_report(data_df, summary_df, issues_df)
    st.download_button(
        "Скачать итоговый Excel",
        data=report_bytes,
        file_name="monitoring_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )


if __name__ == "__main__":
    main()
