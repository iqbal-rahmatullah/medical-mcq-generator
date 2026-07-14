"""Split extracted text into overlapping chunks for BM25 + embedding indexing."""
from __future__ import annotations

import re
from typing import Iterator

from app.corpus.models import Document

_PARA_SPLIT_RE = re.compile(r"\n\s*\n")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> Iterator[Document]:
    # paragraph packing with a hard-split fallback for blocks that
    # have no blank-line breaks (e.g. raw PDF page text).
    paragraphs = [p.strip() for p in _PARA_SPLIT_RE.split(text) if p.strip()]
    if not paragraphs:
        return

    idx = 0
    buffer = ""

    def _flush(chunk_text_value: str) -> Iterator[Document]:
        nonlocal idx
        if chunk_text_value.strip():
            yield Document(
                doc_id=f"{source}#{idx}",
                source=source,
                title=source,
                text=chunk_text_value.strip(),
            )
            idx += 1

    for para in paragraphs:
        if len(para) > chunk_size:
            if buffer:
                yield from _flush(buffer)
                buffer = ""
            for start in range(0, len(para), max(chunk_size - overlap, 1)):
                yield from _flush(para[start : start + chunk_size])
            continue

        candidate = f"{buffer}\n\n{para}" if buffer else para
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        yield from _flush(buffer)
        tail = buffer[-overlap:] if overlap else ""
        buffer = f"{tail}\n\n{para}" if tail else para

    if buffer:
        yield from _flush(buffer)
