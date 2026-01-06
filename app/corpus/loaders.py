from __future__ import annotations

import json
import re
from typing import Iterator

from app.corpus.models import Document


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip())


def load_pubmed_jsonl(path: str) -> Iterator[Document]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            doc_id = normalize_text(str(payload.get("doc_id", "")))
            title = normalize_text(str(payload.get("title", "")))
            abstract = normalize_text(str(payload.get("abstract", "")))
            text = normalize_text(" ".join(part for part in [title, abstract] if part))
            if not doc_id:
                continue
            yield Document(
                doc_id=doc_id,
                source="pubmed",
                title=title,
                text=text,
            )


def load_textbooks_jsonl(path: str) -> Iterator[Document]:
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            doc_id = normalize_text(str(payload.get("doc_id", "")))
            title = normalize_text(str(payload.get("title", "")))
            snippet = normalize_text(str(payload.get("snippet", "")))
            text = normalize_text(" ".join(part for part in [title, snippet] if part))
            if not doc_id:
                continue
            yield Document(
                doc_id=doc_id,
                source="textbook",
                title=title,
                text=text,
            )
