from __future__ import annotations

import logging
from typing import Dict, Iterable, List

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from app.corpus.models import Document

LOGGER = logging.getLogger(__name__)

DEFAULT_QUERY_MODEL = "ncbi/MedCPT-Query-Encoder"
DEFAULT_DOC_MODEL = "ncbi/MedCPT-Article-Encoder"


def _select_device(preferred: str | None = None) -> torch.device:
    if preferred:
        return torch.device(preferred)
    if torch.backends.mps.is_available() and torch.backends.mps.is_built():
        return torch.device("mps")
    return torch.device("cpu")


def _mean_pooling(
    last_hidden: torch.Tensor, attention_mask: torch.Tensor
) -> torch.Tensor:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
    summed = torch.sum(last_hidden * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return vectors / norms


class MedCPTRuntime:
    def __init__(
        self,
        query_model_name: str = DEFAULT_QUERY_MODEL,
        doc_model_name: str = DEFAULT_DOC_MODEL,
        device: str | None = None,
        max_length: int = 512,
        batch_size: int = 8,
    ) -> None:
        self._device = _select_device(device)
        self._max_length = max_length
        self._batch_size = batch_size

        self._query_tokenizer = AutoTokenizer.from_pretrained(query_model_name)
        self._query_model = AutoModel.from_pretrained(query_model_name)
        self._query_model.to(self._device)
        self._query_model.eval()

        self._doc_tokenizer = AutoTokenizer.from_pretrained(doc_model_name)
        self._doc_model = AutoModel.from_pretrained(doc_model_name)
        self._doc_model.to(self._device)
        self._doc_model.eval()

    def encode_query(self, text: str) -> np.ndarray:
        if not text.strip():
            return np.zeros((0,), dtype=np.float32)
        embeddings = self._encode_texts([text], self._query_tokenizer, self._query_model)
        return embeddings[0]

    def encode_docs(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        return self._encode_texts(texts, self._doc_tokenizer, self._doc_model)

    def rerank(self, query: str, docs: List[Document]) -> List[float]:
        if not docs:
            return []

        try:
            query_vec = self.encode_query(query)
            if query_vec.size == 0:
                return [0.0 for _ in docs]
        except Exception as exc: 
            LOGGER.exception("Failed to encode query: %s", exc)
            return [0.0 for _ in docs]

        doc_cache: Dict[str, np.ndarray] = {}
        unique_ids: List[str] = []
        unique_texts: List[str] = []
        for doc in docs:
            if doc.doc_id in doc_cache:
                continue
            text = f"{doc.title} {doc.text}".strip()
            if not text:
                doc_cache[doc.doc_id] = np.zeros_like(query_vec)
                continue
            unique_ids.append(doc.doc_id)
            unique_texts.append(text)

        if unique_texts:
            try:
                doc_embeddings = self.encode_docs(unique_texts)
            except Exception as exc: 
                LOGGER.exception("Failed to encode documents: %s", exc)
                return [0.0 for _ in docs]

            for doc_id, embedding in zip(unique_ids, doc_embeddings):
                doc_cache[doc_id] = embedding

        query_matrix = _normalize_vectors(query_vec.reshape(1, -1))
        scores: List[float] = []
        for doc in docs:
            doc_vec = doc_cache.get(doc.doc_id)
            if doc_vec is None or doc_vec.size == 0:
                scores.append(0.0)
                continue
            doc_matrix = _normalize_vectors(doc_vec.reshape(1, -1))
            score = float(np.dot(query_matrix, doc_matrix.T)[0][0])
            scores.append(score)

        return scores

    def _encode_texts(
        self,
        texts: Iterable[str],
        tokenizer: AutoTokenizer,
        model: AutoModel,
    ) -> np.ndarray:
        embeddings: List[np.ndarray] = []
        text_list = list(texts)
        if not text_list:
            return np.zeros((0, 0), dtype=np.float32)

        for start in range(0, len(text_list), self._batch_size):
            batch = text_list[start : start + self._batch_size]
            inputs = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=self._max_length,
                return_tensors="pt",
            )
            inputs = {key: value.to(self._device) for key, value in inputs.items()}

            with torch.no_grad():
                outputs = model(**inputs)

            pooled = outputs.pooler_output if outputs.pooler_output is not None else None
            if pooled is None:
                pooled = _mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])

            embeddings.append(pooled.detach().cpu().numpy())

        return np.vstack(embeddings)
