from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import settings
from app.corpus.models import Document
from app.retrieval.bm25 import BM25Index
from app.retrieval.medcpt_runtime import MedCPTRuntime
from app.retrieval.query_builder import build_query

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalResult:
    doc_ids: List[str]
    evidence_docs: List[Document]


def rrf_fuse(rank_a: List[str], rank_b: List[str], k_rrf: int = 60) -> List[str]:
    scores: dict[str, float] = {}
    rank_a_pos = {doc_id: idx for idx, doc_id in enumerate(rank_a, start=1)}
    rank_b_pos = {doc_id: idx for idx, doc_id in enumerate(rank_b, start=1)}

    for doc_id, pos in rank_a_pos.items():
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k_rrf + pos)

    for doc_id, pos in rank_b_pos.items():
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k_rrf + pos)

    def _tie_breaker(doc_id: str) -> tuple[float, int, int]:
        return (
            scores[doc_id],
            -rank_a_pos.get(doc_id, 10**9),
            -rank_b_pos.get(doc_id, 10**9),
        )

    return sorted(scores.keys(), key=_tie_breaker, reverse=True)


class Retriever:
    def __init__(
        self,
        bm25_index: BM25Index,
        medcpt_runtime: Optional[MedCPTRuntime] = None,
        retrieval_mode: Optional[str] = None,
        bm25_candidates_top_n: Optional[int] = None,
        rerank_top_n: Optional[int] = None,
        evidence_top_k: Optional[int] = None,
        fusion_enabled: Optional[bool] = None,
        rrf_k: Optional[int] = None,
    ) -> None:
        self._bm25_index = bm25_index
        self._medcpt_runtime = medcpt_runtime
        self._retrieval_mode = retrieval_mode or settings.RETRIEVAL_MODE
        self._bm25_candidates_top_n = (
            bm25_candidates_top_n
            if bm25_candidates_top_n is not None
            else settings.BM25_CANDIDATES_TOP_N
        )
        self._rerank_top_n = rerank_top_n if rerank_top_n is not None else settings.RERANK_TOP_N
        self._evidence_top_k = (
            evidence_top_k if evidence_top_k is not None else settings.EVIDENCE_TOP_K
        )
        self._fusion_enabled = (
            fusion_enabled if fusion_enabled is not None else settings.FUSION_ENABLED
        )
        self._rrf_k = rrf_k if rrf_k is not None else settings.RRF_K

    def retrieve(
        self,
        topic: str,
        competency: str,
        *,
        evidence_top_k: Optional[int] = None,
        query_override: Optional[str] = None,
    ) -> RetrievalResult:
        query = (query_override or "").strip() or build_query(topic, competency)
        candidates_limit = max(self._bm25_candidates_top_n, 0)
        bm25_results = self._bm25_index.search(query, top_k=candidates_limit)
        candidate_docs = [doc for doc, _score in bm25_results]
        doc_lookup = {doc.doc_id: doc for doc in candidate_docs}
        candidate_ids = [doc.doc_id for doc in candidate_docs]
        LOGGER.debug("bm25 candidates: %s", candidate_ids)

        ranked_docs = candidate_docs
        reranked_ids: List[str] = []
        final_ids: List[str] = []

        if self._retrieval_mode == "hybrid_rerank":
            if self._medcpt_runtime is None:
                LOGGER.debug("MedCPT runtime missing; fallback to bm25 ranking")
            elif not candidate_docs:
                LOGGER.debug("No candidates to rerank")
            else:
                scores = self._medcpt_runtime.rerank(query, candidate_docs)
                if len(scores) != len(candidate_docs):
                    LOGGER.debug("Rerank score count mismatch; fallback to bm25 ranking")
                else:
                    scored = sorted(
                        zip(candidate_docs, scores), key=lambda item: item[1], reverse=True
                    )
                    rerank_limit = max(self._rerank_top_n, 0)
                    ranked_docs = [doc for doc, _score in scored[:rerank_limit]]

        if ranked_docs:
            reranked_ids = [doc.doc_id for doc in ranked_docs]
            LOGGER.debug("reranked ids: %s", reranked_ids)

        if self._retrieval_mode == "hybrid_rerank":
            if self._fusion_enabled and reranked_ids:
                final_ids = rrf_fuse(candidate_ids, reranked_ids, k_rrf=self._rrf_k)
            else:
                final_ids = reranked_ids or candidate_ids
        else:
            final_ids = candidate_ids

        final_docs = [doc_lookup[doc_id] for doc_id in final_ids if doc_id in doc_lookup]
        evidence_limit = max(
            self._evidence_top_k if evidence_top_k is None else evidence_top_k,
            0,
        )
        evidence_docs = final_docs[:evidence_limit]
        evidence_ids = [doc.doc_id for doc in evidence_docs]
        LOGGER.debug("final evidence ids: %s", evidence_ids)

        return RetrievalResult(doc_ids=final_ids, evidence_docs=evidence_docs)
