"""Generic multilingual embedding encoder + a stored-embedding reranker.

Replaces the medical-only MedCPTRuntime for domain-agnostic knowledge bases:
same mean-pooling pattern, single E5-style model for both query and passage
(query/passage distinguished by text prefix, per E5 convention).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np

from app.core.config import settings
from app.corpus.models import Document

# torch + transformers are imported lazily inside the functions that need them:
# a cold `import torch` takes ~15-30s, and this module is pulled in at API
# startup (via pipeline). Deferring it keeps `uvicorn` startup near-instant;
# the models only load on the first ingest/generate.

LOGGER = logging.getLogger(__name__)


def _select_device():
    import torch

    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        return torch.device("mps")
    return torch.device("cpu")


def _mean_pooling(last_hidden, attention_mask):
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
    summed = torch.sum(last_hidden * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return vectors / norms


class Embedder:
    def __init__(
        self,
        model_name: Optional[str] = None,
        batch_size: int = 16,
        max_length: int = 512,
    ) -> None:
        from transformers import AutoModel, AutoTokenizer

        self._model_name = model_name or settings.EMBED_MODEL
        self._device = _select_device()
        self._batch_size = batch_size
        self._max_length = max_length
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        self._model = AutoModel.from_pretrained(self._model_name)
        self._model.to(self._device)
        self._model.eval()

    def encode_query(self, text: str) -> np.ndarray:
        if not text.strip():
            return np.zeros((0,), dtype=np.float32)
        return self._encode([f"query: {text}"])[0]

    def encode_docs(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return self._encode([f"passage: {t}" for t in texts])

    def _encode(self, texts: List[str]) -> np.ndarray:
        import torch

        embeddings: List[np.ndarray] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            inputs = self._tokenizer(
                batch, padding=True, truncation=True, max_length=self._max_length, return_tensors="pt"
            )
            inputs = {key: value.to(self._device) for key, value in inputs.items()}
            with torch.no_grad():
                outputs = self._model(**inputs)
            pooled = _mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
            embeddings.append(pooled.detach().cpu().numpy())
        return _normalize(np.vstack(embeddings))


class StoredEmbeddingReranker:
    """Drop-in replacement for MedCPTRuntime.rerank() using precomputed doc embeddings.

    Only the query is encoded at query time; document vectors were computed
    once at ingest time and are looked up by doc_id.
    """

    def __init__(self, embedder: Embedder, doc_embeddings: Dict[str, np.ndarray]) -> None:
        self._embedder = embedder
        self._doc_embeddings = doc_embeddings

    def rerank(self, query: str, docs: List[Document]) -> List[float]:
        if not docs:
            return []
        try:
            query_vec = self._embedder.encode_query(query)
        except Exception as exc:
            LOGGER.exception("Failed to encode query: %s", exc)
            return [0.0 for _ in docs]
        if query_vec.size == 0:
            return [0.0 for _ in docs]

        scores: List[float] = []
        for doc in docs:
            doc_vec = self._doc_embeddings.get(doc.doc_id)
            if doc_vec is None:
                scores.append(0.0)
                continue
            scores.append(float(np.dot(query_vec, doc_vec)))
        return scores
