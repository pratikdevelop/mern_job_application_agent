from pathlib import Path
import pymupdf


def extract_resume_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Resume not found: {path}")
    doc = pymupdf.open(p)
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
