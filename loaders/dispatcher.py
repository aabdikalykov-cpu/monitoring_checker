"""FR-1: Диспетчер загрузчиков по типу файла."""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from loaders.excel_loader import read_excel
from loaders.image_loader import read_image
from loaders.pdf_loader import read_pdf
from loaders.word_loader import read_docx

EXCEL_EXTS = {".xlsx", ".xls", ".xlsm"}
WORD_EXTS = {".docx"}
PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


@dataclass
class LoadedDocument:
    """Результат загрузки одного файла."""

    file_name: str
    file_type: str
    text: str
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    error: str | None = None


def load_document(file_path: str, config: dict) -> LoadedDocument:
    """Загрузить файл и извлечь текст (и таблицы для Excel)."""
    path = Path(file_path)
    ext = path.suffix.lower()
    name = path.name

    try:
        if ext in EXCEL_EXTS:
            content = read_excel(str(path), config.get("header_keywords", []))
            return LoadedDocument(
                file_name=name,
                file_type="excel",
                text=content.text,
                tables=content.sheets,
            )
        if ext in WORD_EXTS:
            return LoadedDocument(
                file_name=name,
                file_type="word",
                text=read_docx(str(path)),
            )
        if ext in PDF_EXTS:
            return LoadedDocument(
                file_name=name,
                file_type="pdf",
                text=read_pdf(
                    str(path),
                    ocr_languages=config.get("ocr_languages", "rus+eng+kaz"),
                    ocr_dpi=config.get("ocr_dpi", 300),
                    text_min_chars=config.get("pdf_text_min_chars", 50),
                ),
            )
        if ext in IMAGE_EXTS:
            return LoadedDocument(
                file_name=name,
                file_type="image",
                text=read_image(str(path), config.get("ocr_languages", "rus+eng+kaz")),
            )
        return LoadedDocument(
            file_name=name,
            file_type="unknown",
            text="",
            error=f"Неподдерживаемый формат: {ext}",
        )
    except Exception as exc:
        return LoadedDocument(
            file_name=name,
            file_type=ext.lstrip("."),
            text="",
            error=str(exc),
        )
