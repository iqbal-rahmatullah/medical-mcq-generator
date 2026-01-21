from __future__ import annotations

import re
from typing import Iterable, List

from app.corpus.models import Document

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9]+")


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


def extract_evidence_spans(
    evidence_docs: Iterable[Document],
    topic: str,
    competency: str,
    max_sentences_per_doc: int = 2,
    max_chars_per_doc: int = 600,
) -> List[Document]:
    keywords = {
        token
        for token in _WORD_RE.findall(f"{topic} {competency}".lower())
        if len(token) > 2
    }
    results: List[Document] = []

    for doc in evidence_docs:
        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(doc.text) if s.strip()]
        if not sentences:
            continue

        span_sentences = max(max_sentences_per_doc, 1)
        if not keywords:
            span = " ".join(sentences[:span_sentences])
        else:
            best_span = ""
            best_score = -1
            best_len = 0
            total = len(sentences)
            for start in range(total):
                span_text = ""
                for end in range(start, min(total, start + span_sentences)):
                    span_text = " ".join(sentences[start : end + 1])
                    span_lower = span_text.lower()
                    score = sum(1 for kw in keywords if kw in span_lower)
                    span_len = len(span_text)
                    if (
                        score > best_score
                        or (score == best_score and (best_len == 0 or span_len < best_len))
                    ):
                        best_span = span_text
                        best_score = score
                        best_len = span_len
            span = best_span or " ".join(sentences[:span_sentences])

        if max_chars_per_doc <= 0:
            continue
        if len(span) > max_chars_per_doc:
            span = span[:max_chars_per_doc].rstrip()
        if not span:
            continue
        results.append(
            Document(
                doc_id=doc.doc_id,
                source=doc.source,
                title=doc.title,
                text=span,
            )
        )

    return results
