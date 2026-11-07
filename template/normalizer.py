"""FR-9: Приведение извлеченных записей к единому утвержденному шаблону."""

import re
from typing import Any

import pandas as pd

# Соответствие колонок шаблона полям borrower_fields
FIELD_TO_COLUMN = {
    "bin_iin": "БИН заемщика",
    "borrower_name": "Наименование заемщика",
    "contract_number": "Номер кредитного договора",
    "contract_date": "Дата кредитного договора",
    "credit_amount": "Сумма кредита",
    "credit_purpose": "Цель кредита",
    "project_address": "Адрес реализации проекта",
    "region": "Регион",
    "monitoring_date": "Дата мониторинга",
    "confirmed_amount": "Подтвержденная сумма целевого использования",
    "purpose_conclusion": "Вывод о целевом использовании",
    "counterparties": "Контрагенты",
    "other_notes": "Прочие замечания",
}


def normalize_amount(value: Any) -> float | None:
    """Нормализовать сумму: убрать пробелы/разделители тысяч, запятую заменить точкой."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    text = re.sub(r"[\s  ]", "", text)  # пробелы всех видов
    text = text.replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_counterparties(counterparties: Any) -> str:
    """Свести список контрагентов в одну строку для ячейки Excel."""
    if not counterparties:
        return ""
    if isinstance(counterparties, str):
        return counterparties
    parts: list[str] = []
    for cp in counterparties:
        if not isinstance(cp, dict):
            parts.append(str(cp))
            continue
        name = cp.get("name") or ""
        bin_value = cp.get("bin") or ""
        amount = cp.get("amount")
        segment = name
        if bin_value:
            segment += f" (БИН {bin_value})"
        if amount is not None:
            segment += f" — {amount}"
        if segment.strip():
            parts.append(segment.strip())
    return "; ".join(parts)


def normalize_record(
    borrower_fields: dict[str, Any],
    bank_name: str,
    row_number: int,
    template_columns: list[str],
) -> dict[str, Any]:
    """Привести одну запись к колонкам шаблона."""
    row: dict[str, Any] = {col: None for col in template_columns}

    if "№" in row:
        row["№"] = row_number
    if "Банк" in row:
        row["Банк"] = bank_name

    for field_name, column in FIELD_TO_COLUMN.items():
        if column not in row:
            continue
        value = borrower_fields.get(field_name)
        if field_name in ("credit_amount", "confirmed_amount"):
            value = normalize_amount(value)
        elif field_name == "counterparties":
            value = format_counterparties(value)
        row[column] = value

    return row


def normalize_to_template(
    records: list[dict[str, Any]],
    bank_names: list[str],
    template_columns: list[str],
) -> pd.DataFrame:
    """Привести список записей к DataFrame по шаблону."""
    rows = [
        normalize_record(fields, bank, i + 1, template_columns)
        for i, (fields, bank) in enumerate(zip(records, bank_names))
    ]
    return pd.DataFrame(rows, columns=template_columns)
