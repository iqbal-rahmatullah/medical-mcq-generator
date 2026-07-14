"""Extract raw text from uploaded knowledge files."""
from __future__ import annotations

from pathlib import Path


def parse_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def parse_docx(path: Path) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def parse_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


_PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".txt": parse_text,
    ".md": parse_text,
}


def parse_file(path: Path) -> str:
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ValueError(f"unsupported_file_type: {path.suffix}")
    return parser(path)
