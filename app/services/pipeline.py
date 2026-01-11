from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from app.core.config import settings
from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.store import DocumentStore
from app.generation.evidence_format import render_evidence
from app.generation.llm_client import LLMClient
from app.generation.prompt_templates import build_prompt
from app.retrieval.bm25 import BM25Index
from app.retrieval.medcpt_runtime import MedCPTRuntime
from app.retrieval.query_builder import build_query
from app.retrieval.retriever import Retriever
from app.schemas.request import GenerateRequestItem
from app.schemas.response import Meta, Options, QuestionItem, QuestionStatus
from app.logging.logger import log_run
from app.verification.gate import ReviewerClient, VerificationResult, verify_questions

LOGGER = logging.getLogger(__name__)

_RETRIEVER: Optional[Retriever] = None
_RETRIEVER_ERROR: Optional[str] = None
_LLM_CLIENT: Optional[LLMClient] = None
_MAX_ATTEMPTS = 2
_REQUOTE_INSTRUCTION = "re-quote exact evidence span"
_V2_FAILED_CHECKS = {
    "evidence_span_mismatch",
    "evidence_span_empty",
    "evidence_doc_missing",
}
_REWRITE_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


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


def _rewrite_query(topic: str, competency: str) -> str:
    base = build_query(topic, competency).strip()
    tokens = _REWRITE_TOKEN_RE.findall(competency)
    if not tokens:
        return base
    return f"{base} {' '.join(tokens)}".strip()


def _summarize_verification_results(
    verification_results: List[VerificationResult],
) -> tuple[Dict[str, int], List[str]]:
    status_counts = {
        "OK": 0,
        "INSUFFICIENT_EVIDENCE": 0,
        "FAILED_VERIFICATION": 0,
    }
    failed_checks = set()
    for result in verification_results:
        status = result.question.status
        status_counts[status] = status_counts.get(status, 0) + 1
        failed_checks.update(result.report.failed_checks)
    return status_counts, sorted(failed_checks)


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
            except Exception as exc:
                LOGGER.exception("Failed to init MedCPT runtime: %s", exc)
                medcpt_runtime = None

        _RETRIEVER = Retriever(index, medcpt_runtime=medcpt_runtime)
        return _RETRIEVER
    except Exception as exc:
        _RETRIEVER_ERROR = f"retriever_init_failed: {exc}"
        LOGGER.exception("Failed to init retriever: %s", exc)
        return None


def run_pipeline_batch(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    retriever = _get_retriever()
    llm_client = _get_llm_client()
    reviewer_client = _get_reviewer_client()
    run_started = time.perf_counter()
    run_id = uuid.uuid4().hex
    run_timestamp = datetime.utcnow().isoformat() + "Z"
    run_log_items: List[Dict[str, object]] = []
    input_batch = [item.model_dump() for item in payload]

    for item in payload:
        try:
            if item.n_questions < 1:
                raise ValueError("n_questions must be >= 1")

            if retriever is None:
                results.extend(build_failure_batch([item], "retriever_unavailable"))
                continue

            attempt_history: List[Dict[str, object]] = []
            attempt_logs: List[Dict[str, object]] = []
            final_questions: Optional[List[QuestionItem]] = None
            initial_top_k = max(settings.EVIDENCE_TOP_K, 0)
            expanded_top_k = max(settings.EVIDENCE_TOP_K_EXPANDED, 0)
            evidence_top_k = initial_top_k
            query_override: Optional[str] = None
            extra_instructions: Optional[str] = None
            attempt_reason = "initial"

            for attempt in range(1, _MAX_ATTEMPTS + 1):
                query_used = (query_override or "").strip() or build_query(
                    item.topic, item.competency
                )
                retrieval_start = time.perf_counter()
                retrieval_result = retriever.retrieve(
                    item.topic,
                    item.competency,
                    evidence_top_k=evidence_top_k,
                    query_override=query_override,
                )
                retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0

                if not retrieval_result.evidence_docs:
                    attempt_logs.append(
                        {
                            "attempt": attempt,
                            "reason": attempt_reason,
                            "query": query_used,
                            "evidence_top_k": evidence_top_k,
                            "prompt_hash": "",
                            "evidence_doc_ids": {
                                "bm25": retrieval_result.bm25_doc_ids,
                                "dense": retrieval_result.dense_doc_ids,
                                "fused": retrieval_result.fused_doc_ids,
                            },
                            "runtime_ms": {
                                "retrieval": retrieval_ms,
                                "llm": 0.0,
                                "verification": 0.0,
                            },
                            "status_counts": {"INSUFFICIENT_EVIDENCE": item.n_questions},
                            "failed_checks": ["insufficient_evidence"],
                        }
                    )
                    attempt_history.append(
                        {
                            "attempt": attempt,
                            "reason": attempt_reason,
                            "query": query_used,
                            "evidence_top_k": evidence_top_k,
                            "retrieval_ms": retrieval_ms,
                            "status_counts": {"INSUFFICIENT_EVIDENCE": item.n_questions},
                            "failed_checks": ["insufficient_evidence"],
                        }
                    )
                    if attempt < _MAX_ATTEMPTS:
                        evidence_top_k = expanded_top_k
                        query_override = _rewrite_query(item.topic, item.competency)
                        attempt_reason = "v3_insufficient"
                        extra_instructions = None
                        continue
                    final_questions = build_failure_batch(
                        [item],
                        "insufficient_evidence",
                        status="INSUFFICIENT_EVIDENCE",
                    )
                    for question in final_questions:
                        question.meta.retrieval.setdefault("retrieval_mode", settings.RETRIEVAL_MODE)
                        question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
                        question.meta.timings_ms.setdefault("llm", 0.0)
                        question.meta.timings_ms.setdefault("verification", 0.0)
                    break

                evidence_text = render_evidence(retrieval_result.evidence_docs)
                prompt = build_prompt(
                    item.topic,
                    item.competency,
                    evidence_text,
                    item.n_questions,
                    extra_instructions=extra_instructions,
                )
                prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                llm_start = time.perf_counter()
                questions = llm_client.generate_mcq(
                    item.topic,
                    item.competency,
                    evidence_text,
                    item.n_questions,
                    extra_instructions=extra_instructions,
                )
                llm_ms = (time.perf_counter() - llm_start) * 1000.0

                verification_start = time.perf_counter()
                verification_results = verify_questions(
                    questions,
                    retrieval_result.evidence_docs,
                    reviewer=reviewer_client,
                    run_reviewer=True,
                )
                verification_ms = (time.perf_counter() - verification_start) * 1000.0

                for result in verification_results:
                    question = result.question
                    question.meta.retrieval.setdefault("doc_ids", retrieval_result.doc_ids)
                    question.meta.retrieval.setdefault("retrieval_mode", settings.RETRIEVAL_MODE)
                    question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
                    question.meta.timings_ms.setdefault("llm", llm_ms)
                    question.meta.timings_ms.setdefault("verification", verification_ms)

                status_counts, failed_checks = _summarize_verification_results(
                    verification_results
                )
                attempt_logs.append(
                    {
                        "attempt": attempt,
                        "reason": attempt_reason,
                        "query": query_used,
                        "evidence_top_k": evidence_top_k,
                        "prompt_hash": prompt_hash,
                        "evidence_doc_ids": {
                            "bm25": retrieval_result.bm25_doc_ids,
                            "dense": retrieval_result.dense_doc_ids,
                            "fused": retrieval_result.fused_doc_ids,
                        },
                        "runtime_ms": {
                            "retrieval": retrieval_ms,
                            "llm": llm_ms,
                            "verification": verification_ms,
                        },
                        "status_counts": status_counts,
                        "failed_checks": failed_checks,
                    }
                )
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "reason": attempt_reason,
                        "query": query_used,
                        "evidence_top_k": evidence_top_k,
                        "retrieval_ms": retrieval_ms,
                        "llm_ms": llm_ms,
                        "verification_ms": verification_ms,
                        "extra_instructions": extra_instructions or "",
                        "status_counts": status_counts,
                        "failed_checks": failed_checks,
                    }
                )

                if status_counts.get("OK", 0) == len(verification_results):
                    final_questions = [result.question for result in verification_results]
                    break

                if attempt < _MAX_ATTEMPTS:
                    if status_counts.get("INSUFFICIENT_EVIDENCE", 0) > 0 or (
                        "missing_evidence" in failed_checks
                    ):
                        evidence_top_k = expanded_top_k
                        query_override = _rewrite_query(item.topic, item.competency)
                        attempt_reason = "v3_insufficient"
                        extra_instructions = None
                        continue
                    if any(check in _V2_FAILED_CHECKS for check in failed_checks):
                        extra_instructions = _REQUOTE_INSTRUCTION
                        attempt_reason = "v2_requote"
                        continue

                final_questions = [result.question for result in verification_results]
                break

            if final_questions is None:
                final_questions = build_failure_batch(
                    [item],
                    "pipeline_error",
                    status="FAILED_VERIFICATION",
                )

            for question in final_questions:
                verification_meta = dict(question.meta.verification or {})
                verification_meta["attempt_history"] = attempt_history
                question.meta.verification = verification_meta

            results.extend(final_questions)
            run_log_items.append(
                {
                    "input": item.model_dump(),
                    "attempts": attempt_logs,
                    "outputs": [question.model_dump() for question in final_questions],
                    "verification_reports": [
                        question.meta.verification.get("gate") for question in final_questions
                    ],
                }
            )
        except ValueError as exc:
            failure_questions = build_failure_batch([item], str(exc), status="FAILED_VERIFICATION")
            results.extend(failure_questions)
            run_log_items.append(
                {
                    "input": item.model_dump(),
                    "attempts": [],
                    "outputs": [question.model_dump() for question in failure_questions],
                    "verification_reports": [
                        question.meta.verification.get("gate") for question in failure_questions
                    ],
                }
            )
        except Exception as exc:
            failure_questions = build_failure_batch(
                [item], f"pipeline_error: {exc}", status="FAILED_VERIFICATION"
            )
            results.extend(failure_questions)
            run_log_items.append(
                {
                    "input": item.model_dump(),
                    "attempts": [],
                    "outputs": [question.model_dump() for question in failure_questions],
                    "verification_reports": [
                        question.meta.verification.get("gate") for question in failure_questions
                    ],
                }
            )

    run_record = {
        "run_id": run_id,
        "timestamp": run_timestamp,
        "input_batch": input_batch,
        "items": run_log_items,
        "runtime_ms": (time.perf_counter() - run_started) * 1000.0,
    }
    try:
        log_run(run_record)
    except Exception as exc:
        LOGGER.warning("Failed to log run: %s", exc)

    return results
