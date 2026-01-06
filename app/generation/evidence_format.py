from __future__ import annotations

import re
from typing import Iterable, List

from app.corpus.models import Document

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return text[: max_chars - 3].rstrip() + "..."

    kept: List[str] = []
    current_len = 0
    for sentence in sentences:
        candidate = sentence if not kept else f"{sentence}"
        next_len = current_len + len(candidate) + (1 if kept else 0)
        if next_len > max_chars:
            break
        kept.append(sentence)
        current_len = next_len

    if not kept:
        return text[: max_chars - 3].rstrip() + "..."

    result = " ".join(kept)
    if len(result) < len(text):
        if len(result) + 3 > max_chars:
            result = result[: max_chars - 3].rstrip()
        result = result + "..."
    return result


def render_evidence(
    evidence_docs: Iterable[Document],
    max_chars_per_doc: int = 800,
    max_total_chars: int = 4000,
) -> str:
    lines: List[str] = []
    total_chars = 0

    for index, doc in enumerate(evidence_docs, start=1):
        prefix = f"[E{index}] (source={doc.source}, id={doc.doc_id}) "
        body = f"Title: {doc.title} Text: {doc.text}"
        body = _truncate_text(body, max_chars_per_doc)
        line = prefix + body

        if max_total_chars > 0:
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            if len(line) > remaining:
                truncated = _truncate_text(line, remaining)
                if not truncated:
                    break
                line = truncated

        lines.append(line)
        total_chars += len(line) + 1

        if max_total_chars > 0 and total_chars >= max_total_chars:
            break

    return "\n".join(lines)
