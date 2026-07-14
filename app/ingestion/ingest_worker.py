"""Background job: parse -> chunk -> BM25 index -> embed -> persist.

Runs once per KB create/edit (FastAPI BackgroundTasks), never during
generation. Generation only ever reads the artifacts this writes.
"""
from __future__ import annotations

import json
import logging
import pickle

import numpy as np

from app.corpus.models import Document
from app.ingestion import knowledge_store as kb_store
from app.ingestion.chunker import chunk_text
from app.ingestion.parsers import parse_file
from app.retrieval.bm25 import BM25Index
from app.retrieval.embedder import Embedder

LOGGER = logging.getLogger(__name__)


def ingest_kb(kb_id: str) -> None:
    try:
        paths = kb_store.kb_paths(kb_id)
        raw_files = sorted(p for p in paths["raw"].iterdir() if p.is_file())

        docs: list[Document] = []
        with paths["chunks"].open("w", encoding="utf-8") as chunks_out:
            for file_path in raw_files:
                try:
                    text = parse_file(file_path)
                except Exception as exc:
                    LOGGER.warning("Failed to parse %s: %s", file_path, exc)
                    continue
                for chunk in chunk_text(text, source=file_path.name):
                    docs.append(chunk)
                    chunks_out.write(
                        json.dumps(
                            {
                                "doc_id": chunk.doc_id,
                                "source": chunk.source,
                                "title": chunk.title,
                                "text": chunk.text,
                            }
                        )
                        + "\n"
                    )

        if not docs:
            kb_store.set_status(kb_id, "failed", error="no_extractable_text")
            _invalidate_retriever_cache(kb_id)
            return

        bm25_index = BM25Index.build(docs)
        with paths["bm25"].open("wb") as handle:
            pickle.dump(bm25_index, handle, protocol=pickle.HIGHEST_PROTOCOL)

        embedder = Embedder()
        texts = [f"{d.title} {d.text}".strip() for d in docs]
        vectors = embedder.encode_docs(texts)
        np.save(paths["embeddings"], vectors.astype(np.float32))

        kb_store.set_status(kb_id, "ready", progress=1.0, n_chunks=len(docs))
    except Exception as exc:
        LOGGER.exception("ingest_kb failed for kb_id=%s: %s", kb_id, exc)
        kb_store.set_status(kb_id, "failed", error=str(exc))
    finally:
        _invalidate_retriever_cache(kb_id)


def _invalidate_retriever_cache(kb_id: str) -> None:
    try:
        from app.services import pipeline

        pipeline.invalidate_retriever_cache(kb_id)
    except Exception:
        pass
