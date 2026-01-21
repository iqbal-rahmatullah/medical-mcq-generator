from __future__ import annotations

import json
import re
from typing import Iterator, Optional

from app.corpus.models import Document

try:
    from datasets import DownloadConfig, load_dataset
except ImportError:  # pragma: no cover - optional dependency
    DownloadConfig = None
    load_dataset = None


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
            body = payload.get("content") or payload.get("contents") or ""
            body = normalize_text(str(body))
            text = body or title
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
            body = payload.get("text") or payload.get("content") or payload.get("contents") or payload.get("snippet") or ""
            body = normalize_text(str(body))
            text = normalize_text(" ".join(part for part in [title, body] if part))
            if not doc_id:
                continue
            yield Document(
                doc_id=doc_id,
                source="textbook",
                title=title,
                text=text,
            )


def load_pubmed_hf(
    dataset_name: str = "MedRAG/pubmed",
    split: str = "train",
    local_files_only: bool = True,
    streaming: bool = True,
    data_dir: Optional[str] = None,
) -> Iterator[Document]:
    if load_dataset is None:
        raise RuntimeError("datasets is not installed; install with `pip install datasets`")

    download_config = None
    if local_files_only and DownloadConfig is not None:
        download_config = DownloadConfig(local_files_only=True)

    dataset = load_dataset(
        dataset_name,
        split=split,
        streaming=streaming,
        data_dir=data_dir,
        download_config=download_config,
    )
    for row in dataset:
        doc_id = normalize_text(str(row.get("doc_id") or row.get("id") or row.get("pmid") or ""))
        title = normalize_text(str(row.get("title", "")))
        body = row.get("content") or row.get("contents") or row.get("text") or row.get("abstract") or ""
        body = normalize_text(str(body))
        text = body or title
        if not doc_id:
            continue
        yield Document(
            doc_id=doc_id,
            source="pubmed",
            title=title,
            text=text,
        )


def load_textbooks_hf(
    dataset_name: str = "MedRAG/textbooks",
    split: str = "train",
    local_files_only: bool = True,
    streaming: bool = True,
    data_dir: Optional[str] = None,
) -> Iterator[Document]:
    if load_dataset is None:
        raise RuntimeError("datasets is not installed; install with `pip install datasets`")

    download_config = None
    if local_files_only and DownloadConfig is not None:
        download_config = DownloadConfig(local_files_only=True)

    dataset = load_dataset(
        dataset_name,
        split=split,
        streaming=streaming,
        data_dir=data_dir,
        download_config=download_config,
    )
    for row in dataset:
        doc_id = normalize_text(str(row.get("doc_id") or row.get("id") or ""))
        title = normalize_text(str(row.get("title", "")))
        body = row.get("text") or row.get("content") or row.get("contents") or row.get("snippet") or ""
        body = normalize_text(str(body))
        text = normalize_text(" ".join(part for part in [title, body] if part))
        if not doc_id:
            continue
        yield Document(
            doc_id=doc_id,
            source="textbook",
            title=title,
            text=text,
        )
