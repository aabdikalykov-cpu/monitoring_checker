"""FR-2: Чтение Excel-отчетов банков (.xlsx, .xls, .xlsm)."""

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class ExcelContent:
    """Содержимое Excel-файла: таблицы по листам и плоский текст."""

    sheets: dict[str, pd.DataFrame] = field(default_factory=dict)
    text: str = ""


def find_header_row(df: pd.DataFrame, keywords: list[str], max_rows: int = 30) -> int:
    """Найти номер строки заголовка по ключевым словам в первых max_rows строках."""
    best_row = 0
    best_score = 0
    rows_to_scan = min(max_rows, len(df))
    for i in range(rows_to_scan):
        row = df.iloc[i]
        row_text = " ".join(str(v).lower() for v in row if pd.notna(v))
        if not row_text.strip():
            continue
        score = sum(1 for kw in keywords if kw in row_text)
        if score > best_score:
            best_score = score
            best_row = i
    return best_row if best_score > 0 else 0


def read_excel(file_path: str, header_keywords: list[str]) -> ExcelContent:
    """Прочитать все листы Excel-файла, определить заголовки и собрать текст."""
    all_sheets = pd.read_excel(file_path, sheet_name=None, header=None, dtype=object)
    result = ExcelContent()
    text_parts: list[str] = []

    for sheet_name, raw_df in all_sheets.items():
        if raw_df.empty:
            continue
        header_row = find_header_row(raw_df, header_keywords)
        header = [
            str(v).strip() if pd.notna(v) else f"col_{j}"
            for j, v in enumerate(raw_df.iloc[header_row])
        ]
        df = raw_df.iloc[header_row + 1 :].reset_index(drop=True)
        df.columns = header
        df = df.dropna(how="all")
        result.sheets[sheet_name] = df

        text_parts.append(f"=== Лист: {sheet_name} ===")
        text_parts.append(" | ".join(str(c) for c in df.columns))
        for _, row in df.iterrows():
            values = [str(v) for v in row if pd.notna(v)]
            if values:
                text_parts.append(" | ".join(values))
        text_parts.append("")

    result.text = "\n".join(text_parts)
    return result
