"""FR-4: Чтение PDF — текстовый слой и OCR для сканов."""

import pdfplumber

from loaders.image_loader import ocr_image


def read_pdf(
    file_path: str,
    ocr_languages: str = "rus+eng+kaz",
    ocr_dpi: int = 300,
    text_min_chars: int = 50,
) -> str:
    """Извлечь текст из PDF постранично; сканы распознать через OCR."""
    parts: list[str] = []

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            parts.append(f"=== Страница {page_num} ===")

            text = page.extract_text() or ""
            if len(text.strip()) >= text_min_chars:
                parts.append(text)
                for table in page.extract_tables():
                    for row in table:
                        cells = [str(c) if c is not None else "" for c in row]
                        parts.append(" | ".join(cells))
            else:
                image = page.to_image(resolution=ocr_dpi).original
                ocr_text = ocr_image(image, ocr_languages)
                parts.append(ocr_text)

            parts.append("")

    return "\n".join(parts)
