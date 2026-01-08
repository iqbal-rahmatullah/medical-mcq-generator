from __future__ import annotations

import logging
import time
from typing import List, Optional

from app.core.config import settings
from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.store import DocumentStore
from app.generation.evidence_format import render_evidence
from app.generation.llm_client import LLMClient
from app.retrieval.bm25 import BM25Index
from app.retrieval.medcpt_runtime import MedCPTRuntime
from app.retrieval.retriever import Retriever
from app.schemas.request import GenerateRequestItem
from app.schemas.response import Meta, Options, QuestionItem, QuestionStatus
from app.verification.gate import ReviewerClient, verify_questions

LOGGER = logging.getLogger(__name__)

_RETRIEVER: Optional[Retriever] = None
_RETRIEVER_ERROR: Optional[str] = None
_LLM_CLIENT: Optional[LLMClient] = None


def _build_failure_question(
    item: GenerateRequestItem,
    status: QuestionStatus,
    error_message: str,
) -> QuestionItem:
    meta = Meta(
        retrieval={"error": error_message},
        verification={"error": error_message},
        timings_ms={},
    )
    return QuestionItem(
        topic=item.topic,
        competency=item.competency,
        stem="",
        options=Options(A="", B="", C="", D=""),
        answer_key="A",
        explanation=error_message,
        evidence=[],
        status=status,
        meta=meta,
    )


def build_failure_batch(
    payload: List[GenerateRequestItem],
    error_message: str,
    status: QuestionStatus = "FAILED_VERIFICATION",
) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    for item in payload:
        count = max(item.n_questions, 1)
        for _ in range(count):
            results.append(_build_failure_question(item, status, error_message))
    return results


def _get_llm_client() -> LLMClient:
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        _LLM_CLIENT = LLMClient()
    return _LLM_CLIENT


def _get_reviewer_client() -> Optional[ReviewerClient]:
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    if provider in ("groq", "groq_sdk", "groq_cloud"):
        if not (settings.GROQ_API_KEY or settings.LLM_API_KEY):
            return None
    elif provider in ("openai_compatible", "openai", "gemini_sdk", "gemini", "google_genai"):
        if not settings.LLM_API_KEY:
            return None
    if not settings.LLM_MODEL:
        return None
    return ReviewerClient(_get_llm_client())


def _load_corpus() -> DocumentStore:
    store = DocumentStore()
    pubmed_limit = max(settings.CORPUS_PUBMED_MAX_DOCS, 0)
    pubmed_count = 0
    textbook_limit = max(settings.CORPUS_TEXTBOOKS_MAX_DOCS, 0)
    textbook_count = 0

    try:
        for doc in load_pubmed_hf(
            settings.CORPUS_PUBMED_HF_DATASET,
            local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
            streaming=settings.CORPUS_HF_STREAMING,
        ):
            if store.add(doc):
                pubmed_count += 1
            if pubmed_limit and pubmed_count >= pubmed_limit:
                break
    except Exception as exc:
        LOGGER.warning("Pubmed HF load failed: %s", exc)

    try:
        for doc in load_textbooks_hf(
            settings.CORPUS_TEXTBOOKS_HF_DATASET,
            local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
            streaming=settings.CORPUS_HF_STREAMING,
        ):
            if store.add(doc):
                textbook_count += 1
            if textbook_limit and textbook_count >= textbook_limit:
                break
    except Exception as exc:
        LOGGER.warning("Textbooks HF load failed: %s", exc)

    return store


def _get_retriever() -> Optional[Retriever]:
    global _RETRIEVER, _RETRIEVER_ERROR
    if _RETRIEVER is not None or _RETRIEVER_ERROR:
        return _RETRIEVER

    try:
        store = _load_corpus()
        if len(store) == 0:
            _RETRIEVER_ERROR = "corpus_empty"
            LOGGER.error("Corpus is empty; check HF dataset cache or config")
            return None

        index = BM25Index.build(store.iter_docs())
        medcpt_runtime = None
        if settings.RETRIEVAL_MODE == "hybrid_rerank":
            try:
                medcpt_runtime = MedCPTRuntime()
            except Exception as exc:  # pragma: no cover - defensive path
                LOGGER.exception("Failed to init MedCPT runtime: %s", exc)
                medcpt_runtime = None

        _RETRIEVER = Retriever(index, medcpt_runtime=medcpt_runtime)
        return _RETRIEVER
    except Exception as exc:  # pragma: no cover - defensive path
        _RETRIEVER_ERROR = f"retriever_init_failed: {exc}"
        LOGGER.exception("Failed to init retriever: %s", exc)
        return None


def run_pipeline_batch(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    retriever = _get_retriever()
    llm_client = _get_llm_client()
    reviewer_client = _get_reviewer_client()

    for item in payload:
        try:
            if item.n_questions < 1:
                raise ValueError("n_questions must be >= 1")

            if retriever is None:
                results.extend(build_failure_batch([item], "retriever_unavailable"))
                continue

            retrieval_start = time.perf_counter()
            retrieval_result = retriever.retrieve(item.topic, item.competency)
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0

            if not retrieval_result.evidence_docs:
                results.extend(
                    build_failure_batch(
                        [item],
                        "insufficient_evidence",
                        status="INSUFFICIENT_EVIDENCE",
                    )
                )
                continue

            evidence_text = render_evidence(retrieval_result.evidence_docs)
            llm_start = time.perf_counter()
            questions = llm_client.generate_mcq(
                item.topic,
                item.competency,
                evidence_text,
                item.n_questions,
            )
            llm_ms = (time.perf_counter() - llm_start) * 1000.0

            verification_results = verify_questions(
                questions,
                retrieval_result.evidence_docs,
                reviewer=reviewer_client,
                run_reviewer=True,
            )

            for result in verification_results:
                question = result.question
                question.meta.retrieval.setdefault("doc_ids", retrieval_result.doc_ids)
                question.meta.retrieval.setdefault("retrieval_mode", settings.RETRIEVAL_MODE)
                question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
                question.meta.timings_ms.setdefault("llm", llm_ms)

            results.extend(result.question for result in verification_results)
        except ValueError as exc:
            results.extend(build_failure_batch([item], str(exc), status="FAILED_VERIFICATION"))
        except Exception as exc:
            results.extend(
                build_failure_batch([item], f"pipeline_error: {exc}", status="FAILED_VERIFICATION")
            )

    return results
