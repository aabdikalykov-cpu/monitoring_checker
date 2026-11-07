"""FR-10: Формирование итогового Excel-отчета (Свод / Данные / Замечания)."""

from dataclasses import asdict
from io import BytesIO
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from analyzers.claude_analyzer import Issue

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SEVERITY_FILLS = {
    "high": PatternFill("solid", fgColor="F8CBAD"),
    "medium": PatternFill("solid", fgColor="FFE699"),
    "low": PatternFill("solid", fgColor="C6EFCE"),
}


def _autosize_and_style(ws) -> None:
    """Стилизовать заголовок, закрепить шапку, подобрать ширину колонок."""
    if ws.max_row < 1:
        return
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"

    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        max_length = 0
        for cell in ws[letter]:
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[letter].width = min(max(max_length + 2, 10), 60)


def build_summary_df(
    total: int,
    ok: int,
    issues: int,
    insufficient: int,
    extra_rows: list[tuple[str, Any]] | None = None,
) -> pd.DataFrame:
    """Сформировать таблицу листа «Свод»."""
    rows = [
        ("Всего записей", total),
        ("Без замечаний", ok),
        ("С замечаниями", issues),
        ("Недостаточно данных", insufficient),
    ]
    if extra_rows:
        rows.extend(extra_rows)
    return pd.DataFrame(rows, columns=["Показатель", "Значение"])


def build_issues_df(
    issues_per_record: list[tuple[int, str, str, list[Issue]]],
) -> pd.DataFrame:
    """Сформировать таблицу листа «Замечания».

    issues_per_record: список кортежей (№ записи, заемщик, банк, замечания).
    """
    rows = []
    for record_no, borrower, bank, issues in issues_per_record:
        for issue in issues:
            rows.append(
                {
                    "№": record_no,
                    "Заемщик": borrower,
                    "Банк": bank,
                    "Критичность": issue.severity,
                    "Проверка": issue.check,
                    "Поле": issue.field,
                    "Описание": issue.description,
                    "Обоснование": issue.evidence,
                }
            )
    columns = ["№", "Заемщик", "Банк", "Критичность", "Проверка", "Поле", "Описание", "Обоснование"]
    return pd.DataFrame(rows, columns=columns)


def export_report(
    data_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    issues_df: pd.DataFrame,
) -> bytes:
    """Сформировать итоговый Excel и вернуть байты файла."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Свод", index=False)
        data_df.to_excel(writer, sheet_name="Данные", index=False)
        issues_df.to_excel(writer, sheet_name="Замечания", index=False)

        for sheet_name in ("Свод", "Данные", "Замечания"):
            _autosize_and_style(writer.sheets[sheet_name])

        # Подсветка критичности на листе «Замечания»
        ws = writer.sheets["Замечания"]
        if ws.max_row >= 2:
            severity_col = None
            for idx, cell in enumerate(ws[1], start=1):
                if cell.value == "Критичность":
                    severity_col = idx
                    break
            if severity_col:
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
                    cell = row[severity_col - 1]
                    fill = SEVERITY_FILLS.get(str(cell.value))
                    if fill:
                        cell.fill = fill

    return buffer.getvalue()


def issue_to_dict(issue: Issue) -> dict[str, Any]:
    """Сериализовать Issue (для промежуточного хранения)."""
    return asdict(issue)
