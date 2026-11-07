"""FR-5: OCR изображений и сканов (Tesseract, rus+eng+kaz)."""

import io
import shutil
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

if not shutil.which("tesseract"):
    windows_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if windows_tesseract.is_file():
        pytesseract.pytesseract.tesseract_cmd = str(windows_tesseract)

TESSDATA_DIR = Path(__file__).resolve().parent.parent / "tessdata"
TESSDATA_CONFIG = f"--tessdata-dir {TESSDATA_DIR.as_posix()}" if TESSDATA_DIR.is_dir() else ""


def ocr_image(image: Image.Image, languages: str = "rus+eng+kaz") -> str:
    """Распознать текст с PIL-изображения с предобработкой."""
    gray = image.convert("L")
    gray = ImageOps.autocontrast(gray)
    return pytesseract.image_to_string(gray, lang=languages, config=TESSDATA_CONFIG)


def read_image(file_path: str, languages: str = "rus+eng+kaz") -> str:
    """Открыть файл изображения и распознать текст."""
    with Image.open(file_path) as img:
        return ocr_image(img, languages)


def ocr_image_bytes(data: bytes, languages: str = "rus+eng+kaz") -> str:
    """Распознать текст из байтов изображения."""
    with Image.open(io.BytesIO(data)) as img:
        return ocr_image(img, languages)
