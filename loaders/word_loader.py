"""FR-3: Чтение Word-документов (.docx)."""

from docx import Document


def read_docx(file_path: str) -> str:
    """Извлечь параграфы и таблицы из .docx в плоский текст."""
    doc = Document(file_path)
    parts: list[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            parts.append(text)

    for table_idx, table in enumerate(doc.tables, start=1):
        parts.append(f"=== Таблица {table_idx} ===")
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            parts.append(" | ".join(cells))
        parts.append("")

    return "\n".join(parts)
