from pathlib import Path

try:
    import pytesseract
except Exception:
    pytesseract = None


def extract_text(image_path: Path, lang: str, tesseract_cmd: str, max_chars: int = 4000) -> str:
    if pytesseract is None:
        return ""
    try:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        text = pytesseract.image_to_string(str(image_path), lang=lang).strip()
        if len(text) > max_chars:
            return text[:max_chars] + "\n...[OCR обрезан]"
        return text
    except Exception as exc:
        return f"[OCR error: {exc}]"
