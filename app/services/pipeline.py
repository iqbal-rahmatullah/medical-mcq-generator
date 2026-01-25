from __future__ import annotations

import hashlib
import json
import logging
import pickle
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from app.core.config import settings
from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.models import Document
from app.corpus.store import DocumentStore
from app.generation.evidence_format import extract_evidence_spans, render_evidence
from app.generation.llm_client import LLMClient
from app.generation.prompt_templates import build_prompt
from app.retrieval.bm25 import BM25Index
from app.retrieval.medcpt_runtime import MedCPTRuntime
from app.retrieval.pubmed_web import fetch_pubmed_documents
from app.retrieval.query_builder import build_query
from app.retrieval.retriever import RetrievalResult, Retriever
from app.schemas.request import GenerateRequestItem
from app.schemas.response import Meta, Options, QuestionItem, QuestionStatus
from app.logging.logger import log_run
from app.logging.question_bank import append_question_bank, load_question_bank
from app.verification.gate import ReviewerClient, VerificationResult, verify_questions

LOGGER = logging.getLogger(__name__)

_RETRIEVER: Optional[Retriever] = None
_RETRIEVER_ERROR: Optional[str] = None
_LLM_CLIENT: Optional[LLMClient] = None
_MAX_ATTEMPTS = max(settings.LLM_MAX_ATTEMPTS, 1)
_CANDIDATES_PER_ATTEMPT = max(settings.LLM_CANDIDATES, 1)
_MAX_DEDUP_ATTEMPTS = max(settings.LLM_DEDUP_ATTEMPTS, 1)
_REQUOTE_INSTRUCTION = "re-quote exact evidence span"
_STRICT_JSON_INSTRUCTION = (
    "Return only valid JSON for the requested schema. "
    "Do not include extra text, markdown, or code fences. "
    "Ensure answer_key is one of A/B/C/D; if insufficient evidence, use 'A'. "
    "Do not omit any required keys; do not return empty options or an empty stem."
)
_EVIDENCE_FOCUS_INSTRUCTION = (
    "Ensure the correct answer is directly supported by the evidence and "
    "quote the exact supporting span."
)
_DEDUPLICATE_INSTRUCTION = (
    "Generate a different question from previous ones; avoid repeating stems."
)
_GENERIC_FAILURE_MESSAGE = "generation_failed"
_V2_FAILED_CHECKS = {
    "evidence_span_mismatch",
    "evidence_span_empty",
    "evidence_doc_missing",
}
_REWRITE_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _summarize_failure_reason(question: QuestionItem) -> str:
    verification_meta = question.meta.verification or {}
    retrieval_meta = question.meta.retrieval or {}
    reason = (
        verification_meta.get("error")
        or retrieval_meta.get("error")
        or question.explanation
        or question.status
    )
    return str(reason)


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


def _fetch_pubmed_fallback(query: str) -> List[Document]:
    if not settings.PUBMED_WEB_ENABLED:
        return []
    return fetch_pubmed_documents(
        query,
        max_results=max(settings.PUBMED_WEB_MAX_RESULTS, 0),
        api_key=(settings.PUBMED_API_KEY or "").strip() or None,
        email=(settings.PUBMED_EMAIL or "").strip() or None,
        timeout_sec=max(settings.PUBMED_WEB_TIMEOUT_SEC, 1.0),
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
    provider = (
        settings.REVIEWER_PROVIDER or settings.LLM_PROVIDER or ""
    ).strip().lower()
    model = (settings.REVIEWER_MODEL or settings.LLM_MODEL or "").strip()
    if not model:
        return None

    api_base = (settings.REVIEWER_API_BASE or settings.LLM_API_BASE or "").strip()
    timeout_sec = settings.REVIEWER_TIMEOUT_SEC or settings.LLM_TIMEOUT_SEC
    api_key = (settings.REVIEWER_API_KEY or "").strip()
    groq_api_key = ""
    cerebras_api_key = ""

    if provider in ("groq", "groq_sdk", "groq_cloud"):
        groq_api_key = api_key or (settings.GROQ_API_KEY or "").strip()
        api_key = api_key or (settings.LLM_API_KEY or "").strip()
        if not (groq_api_key or api_key):
            return None
    elif provider in ("cerebras", "cerebras_sdk", "cerebras_cloud"):
        cerebras_api_key = api_key or (settings.CEREBRAS_API_KEY or "").strip()
        api_key = api_key or (settings.LLM_API_KEY or "").strip()
        if not (cerebras_api_key or api_key):
            return None
    elif provider in ("openai_compatible", "openai", "gemini_sdk", "gemini", "google_genai"):
        api_key = api_key or (settings.LLM_API_KEY or "").strip()
        if not api_key:
            return None

    reviewer_llm = LLMClient(
        api_key=api_key or None,
        api_base=api_base or None,
        model=model,
        timeout_sec=timeout_sec,
        provider=provider or None,
        groq_api_key=groq_api_key or None,
        cerebras_api_key=cerebras_api_key or None,
        fallback_targets_json=settings.REVIEWER_FALLBACKS,
    )
    return ReviewerClient(reviewer_llm)


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


def _normalize_stem(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _matches_topic_competency(
    question: QuestionItem, topic: str, competency: str
) -> bool:
    return (
        question.topic.strip().lower() == topic.strip().lower()
        and question.competency.strip().lower() == competency.strip().lower()
    )


def _select_bank_question(
    bank_questions: List[QuestionItem],
    topic: str,
    competency: str,
    avoid_normalized: set[str],
    allow_any_topic: bool,
) -> Optional[QuestionItem]:
    candidates = [
        question
        for question in bank_questions
        if question.status == "OK"
        and question.stem
        and _normalize_stem(question.stem) not in avoid_normalized
    ]
    if not candidates:
        return None
    matching = [q for q in candidates if _matches_topic_competency(q, topic, competency)]
    if matching:
        return QuestionItem.model_validate(matching[0].model_dump())
    if allow_any_topic:
        return QuestionItem.model_validate(candidates[0].model_dump())
    return None


def _merge_instructions(*parts: Optional[str]) -> Optional[str]:
    merged = " ".join(part.strip() for part in parts if part and part.strip())
    return merged or None


def _build_dedupe_instruction(avoid_stems: List[str], limit: int = 2) -> Optional[str]:
    if not avoid_stems:
        return None
    snippets: List[str] = []
    for stem in avoid_stems[-limit:]:
        snippet = stem.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = f"{snippet[:117].rstrip()}..."
        if snippet:
            snippets.append(snippet)
    if not snippets:
        return _DEDUPLICATE_INSTRUCTION
    return f"{_DEDUPLICATE_INSTRUCTION} Avoid these stems: {'; '.join(snippets)}."


def _get_llm_error_reason(question: QuestionItem) -> Optional[str]:
    for meta in (question.meta.verification, question.meta.retrieval):
        if isinstance(meta, dict):
            error = meta.get("error")
            if isinstance(error, str) and error.strip():
                return error
    return None


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


def _is_dev_environment() -> bool:
    env = (settings.environment or "").strip().lower()
    return env in {"local", "development", "dev"}


def _get_retriever_cache_path() -> Optional[Path]:
    cache_path = (settings.RETRIEVER_CACHE_PATH or "").strip()
    if not cache_path:
        return None
    return Path(cache_path).expanduser()


def _build_retriever_cache_fingerprint() -> str:
    payload = {
        "corpus_schema_version": 2,
        "pubmed_dataset": settings.CORPUS_PUBMED_HF_DATASET,
        "textbooks_dataset": settings.CORPUS_TEXTBOOKS_HF_DATASET,
        "pubmed_max_docs": settings.CORPUS_PUBMED_MAX_DOCS,
        "textbooks_max_docs": settings.CORPUS_TEXTBOOKS_MAX_DOCS,
        "hf_local_only": settings.CORPUS_HF_LOCAL_ONLY,
        "hf_streaming": settings.CORPUS_HF_STREAMING,
        "bm25_k1": 1.5,
        "bm25_b": 0.75,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_cached_bm25_index() -> Optional[BM25Index]:
    if not _is_dev_environment():
        return None
    cache_path = _get_retriever_cache_path()
    if cache_path is None or not cache_path.exists():
        return None
    try:
        with cache_path.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            return None
        if payload.get("fingerprint") != _build_retriever_cache_fingerprint():
            return None
        index = payload.get("bm25_index")
        if isinstance(index, BM25Index):
            LOGGER.info("Loaded retriever cache from %s", cache_path)
            return index
    except Exception as exc:
        LOGGER.warning("Failed to load retriever cache: %s", exc)
    return None


def _write_cached_bm25_index(index: BM25Index) -> None:
    if not _is_dev_environment():
        return
    cache_path = _get_retriever_cache_path()
    if cache_path is None:
        return
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fingerprint": _build_retriever_cache_fingerprint(),
            "bm25_index": index,
        }
        with cache_path.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        LOGGER.info("Saved retriever cache to %s", cache_path)
    except Exception as exc:
        LOGGER.warning("Failed to write retriever cache: %s", exc)


def _get_retriever() -> Optional[Retriever]:
    global _RETRIEVER, _RETRIEVER_ERROR
    if _RETRIEVER is not None or _RETRIEVER_ERROR:
        return _RETRIEVER

    try:
        index = _load_cached_bm25_index()
        if index is None:
            store = _load_corpus()
            if len(store) == 0:
                _RETRIEVER_ERROR = "corpus_empty"
                LOGGER.error("Corpus is empty; check HF dataset cache or config")
                return None
            index = BM25Index.build(store.iter_docs())
            _write_cached_bm25_index(index)
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


def _generate_single_question(
    item: GenerateRequestItem,
    retriever: Retriever,
    llm_client: LLMClient,
    reviewer_client: Optional[ReviewerClient],
    avoid_stems: List[str],
    used_doc_ids: Optional[set[str]] = None,
) -> tuple[QuestionItem, List[Dict[str, object]]]:
    attempt_history: List[Dict[str, object]] = []
    attempt_logs: List[Dict[str, object]] = []
    final_question: Optional[QuestionItem] = None
    initial_top_k = max(settings.EVIDENCE_TOP_K, 0)
    expanded_top_k = max(settings.EVIDENCE_TOP_K_EXPANDED, 0)
    evidence_top_k = initial_top_k
    query_override: Optional[str] = None
    extra_instructions: Optional[str] = None
    attempt_reason = "initial"
    override_docs: Optional[List[Document]] = None
    override_reason: Optional[str] = None
    override_retrieval_ms = 0.0
    track_doc_ids = used_doc_ids is not None
    doc_id_tracker = used_doc_ids if used_doc_ids is not None else set()
    final_evidence_doc_ids: List[str] = []

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        query_used = (query_override or "").strip() or build_query(
            item.topic, item.competency
        )
        attempt_reason_used = attempt_reason
        retrieval_mode = settings.RETRIEVAL_MODE
        web_retrieval_ms = 0.0
        pubmed_attempted = False
        pubmed_docs_count = 0

        if override_docs is not None:
            retrieval_mode = "pubmed_web"
            attempt_reason_used = override_reason or attempt_reason
            retrieval_result = RetrievalResult(
                doc_ids=[doc.doc_id for doc in override_docs],
                evidence_docs=override_docs,
                bm25_doc_ids=[],
                dense_doc_ids=[],
                fused_doc_ids=[doc.doc_id for doc in override_docs],
            )
            retrieval_ms = override_retrieval_ms
        else:
            retrieval_start = time.perf_counter()
            retrieval_result = retriever.retrieve(
                item.topic,
                item.competency,
                evidence_top_k=evidence_top_k,
                query_override=query_override,
                exclude_doc_ids=doc_id_tracker if doc_id_tracker else None,
            )
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0

            if not retrieval_result.evidence_docs:
                web_start = time.perf_counter()
                pubmed_attempted = True
                pubmed_docs = _fetch_pubmed_fallback(query_used)
                web_retrieval_ms = (time.perf_counter() - web_start) * 1000.0
                retrieval_ms += web_retrieval_ms
                pubmed_docs_count = len(pubmed_docs)
                if pubmed_docs:
                    retrieval_mode = "pubmed_web"
                    attempt_reason_used = "pubmed_web_fallback"
                    override_docs = pubmed_docs
                    override_reason = "pubmed_web_fallback"
                    override_retrieval_ms = web_retrieval_ms
                    retrieval_result = RetrievalResult(
                        doc_ids=[doc.doc_id for doc in pubmed_docs],
                        evidence_docs=pubmed_docs,
                        bm25_doc_ids=[],
                        dense_doc_ids=[],
                        fused_doc_ids=[doc.doc_id for doc in pubmed_docs],
                    )

        if not retrieval_result.evidence_docs:
            attempt_logs.append(
                {
                    "attempt": attempt,
                    "reason": attempt_reason_used,
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
                    "retrieval_mode": retrieval_mode,
                    "pubmed_web": {
                        "attempted": pubmed_attempted,
                        "docs": pubmed_docs_count,
                        "runtime_ms": web_retrieval_ms,
                    },
                    "status_counts": {"INSUFFICIENT_EVIDENCE": 1},
                    "failed_checks": ["insufficient_evidence"],
                }
            )
            attempt_history.append(
                {
                    "attempt": attempt,
                    "reason": attempt_reason_used,
                    "query": query_used,
                    "evidence_top_k": evidence_top_k,
                    "retrieval_ms": retrieval_ms,
                    "retrieval_mode": retrieval_mode,
                    "pubmed_web": {
                        "attempted": pubmed_attempted,
                        "docs": pubmed_docs_count,
                        "runtime_ms": web_retrieval_ms,
                    },
                    "status_counts": {"INSUFFICIENT_EVIDENCE": 1},
                    "failed_checks": ["insufficient_evidence"],
                }
            )
            if attempt < _MAX_ATTEMPTS:
                evidence_top_k = expanded_top_k
                query_override = _rewrite_query(item.topic, item.competency)
                attempt_reason = "v3_insufficient"
                extra_instructions = None
                continue
            final_question = _build_failure_question(
                item,
                status="INSUFFICIENT_EVIDENCE",
                error_message="insufficient_evidence",
            )
            final_question.meta.retrieval.setdefault(
                "retrieval_mode", settings.RETRIEVAL_MODE
            )
            final_question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
            final_question.meta.timings_ms.setdefault("llm", 0.0)
            final_question.meta.timings_ms.setdefault("verification", 0.0)
            break

        evidence_docs = list(retrieval_result.evidence_docs)
        if avoid_stems and evidence_docs:
            offset = len(avoid_stems) % len(evidence_docs)
            if offset:
                evidence_docs = evidence_docs[offset:] + evidence_docs[:offset]
        evidence_reused = False
        if doc_id_tracker:
            fresh_docs = [
                doc for doc in evidence_docs if doc.doc_id not in doc_id_tracker
            ]
            if fresh_docs:
                evidence_docs = fresh_docs
            else:
                evidence_reused = True
                if attempt < _MAX_ATTEMPTS:
                    did_adjust = False
                    if evidence_top_k < expanded_top_k:
                        evidence_top_k = expanded_top_k
                        did_adjust = True
                    if not query_override:
                        query_override = _rewrite_query(item.topic, item.competency)
                        did_adjust = True
                    if did_adjust:
                        attempt_reason = "v8_evidence_diversity"
                        extra_instructions = None
                        continue
        evidence_docs_for_prompt = evidence_docs
        if settings.EVIDENCE_FIRST:
            extracted_docs = extract_evidence_spans(
                evidence_docs,
                item.topic,
                item.competency,
                max_sentences_per_doc=settings.EVIDENCE_FIRST_MAX_SENTENCES,
                max_chars_per_doc=settings.EVIDENCE_FIRST_MAX_CHARS,
            )
            if extracted_docs:
                evidence_docs_for_prompt = extracted_docs
        evidence_doc_ids = [doc.doc_id for doc in evidence_docs_for_prompt]
        dedupe_instruction = _build_dedupe_instruction(avoid_stems)
        combined_instructions = _merge_instructions(extra_instructions, dedupe_instruction)
        evidence_text = render_evidence(
            evidence_docs_for_prompt,
            max_chars_per_doc=settings.EVIDENCE_MAX_CHARS_PER_DOC,
            max_total_chars=settings.EVIDENCE_MAX_TOTAL_CHARS,
        )
        candidate_count = _CANDIDATES_PER_ATTEMPT
        prompt = build_prompt(
            item.topic,
            item.competency,
            evidence_text,
            candidate_count,
            extra_instructions=combined_instructions,
        )
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        llm_start = time.perf_counter()
        questions = llm_client.generate_mcq(
            item.topic,
            item.competency,
            evidence_text,
            candidate_count,
            extra_instructions=combined_instructions,
        )
        llm_ms = (time.perf_counter() - llm_start) * 1000.0

        verification_start = time.perf_counter()
        verification_docs = evidence_docs_for_prompt
        verification_results = verify_questions(
            questions,
            verification_docs,
            reviewer=reviewer_client,
            run_reviewer=True,
        )
        verification_ms = (time.perf_counter() - verification_start) * 1000.0

        for result in verification_results:
            question = result.question
            question.meta.retrieval.setdefault("doc_ids", retrieval_result.doc_ids)
            question.meta.retrieval.setdefault("evidence_doc_ids", evidence_doc_ids)
            question.meta.retrieval.setdefault("retrieval_mode", retrieval_mode)
            question.meta.timings_ms.setdefault("retrieval", retrieval_ms)
            question.meta.timings_ms.setdefault("llm", llm_ms)
            question.meta.timings_ms.setdefault("verification", verification_ms)

        normalized_avoid = {_normalize_stem(stem) for stem in avoid_stems}
        candidate_infos = []
        for candidate_index, result in enumerate(verification_results):
            question = result.question
            normalized_stem = _normalize_stem(question.stem or "")
            is_duplicate = bool(normalized_stem and normalized_stem in normalized_avoid)
            candidate_failed_checks = list(result.report.failed_checks)
            if is_duplicate:
                candidate_failed_checks = sorted(
                    set(candidate_failed_checks) | {"duplicate_question"}
                )
            candidate_infos.append(
                {
                    "index": candidate_index,
                    "question": question,
                    "failed_checks": candidate_failed_checks,
                    "is_duplicate": is_duplicate,
                }
            )

        selected = next(
            (
                info
                for info in candidate_infos
                if info["question"].status == "OK" and not info["failed_checks"]
            ),
            None,
        )
        if selected is None:
            selected = min(
                candidate_infos,
                key=lambda info: (
                    0 if info["question"].status == "OK" else 1,
                    len(info["failed_checks"]),
                    info["index"],
                ),
            )

        question_result = selected["question"]
        is_duplicate = selected["is_duplicate"]
        selected_failed_checks = selected["failed_checks"]
        llm_error = _get_llm_error_reason(question_result)

        status_counts, aggregate_failed_checks = _summarize_verification_results(
            verification_results
        )
        if is_duplicate:
            aggregate_failed_checks = sorted(
                set(aggregate_failed_checks) | {"duplicate_question"}
            )
        attempt_logs.append(
            {
                "attempt": attempt,
                "reason": attempt_reason_used,
                "query": query_used,
                "evidence_top_k": evidence_top_k,
                "candidate_count": candidate_count,
                "selected_index": selected["index"] + 1,
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
                "retrieval_mode": retrieval_mode,
                "pubmed_web": {
                    "attempted": pubmed_attempted,
                    "docs": pubmed_docs_count,
                    "runtime_ms": web_retrieval_ms,
                },
                "status_counts": status_counts,
                "failed_checks": selected_failed_checks,
                "failed_checks_all": aggregate_failed_checks,
                "evidence_doc_ids_used": evidence_doc_ids,
                "evidence_reused": evidence_reused,
            }
        )
        attempt_history.append(
            {
                "attempt": attempt,
                "reason": attempt_reason_used,
                "query": query_used,
                "evidence_top_k": evidence_top_k,
                "candidate_count": candidate_count,
                "selected_index": selected["index"] + 1,
                "retrieval_ms": retrieval_ms,
                "llm_ms": llm_ms,
                "verification_ms": verification_ms,
                "extra_instructions": extra_instructions or "",
                "retrieval_mode": retrieval_mode,
                "pubmed_web": {
                    "attempted": pubmed_attempted,
                    "docs": pubmed_docs_count,
                    "runtime_ms": web_retrieval_ms,
                },
                "status_counts": status_counts,
                "failed_checks": selected_failed_checks,
                "failed_checks_all": aggregate_failed_checks,
                "evidence_doc_ids_used": evidence_doc_ids,
                "evidence_reused": evidence_reused,
            }
        )

        if question_result.status == "OK" and not selected_failed_checks:
            final_question = question_result
            final_evidence_doc_ids = evidence_doc_ids
            break

        if attempt < _MAX_ATTEMPTS:
            if (
                retrieval_mode != "pubmed_web"
                and (
                    "topic_coverage" in selected_failed_checks
                    or question_result.status == "INSUFFICIENT_EVIDENCE"
                )
            ):
                web_start = time.perf_counter()
                pubmed_attempted = True
                pubmed_docs = _fetch_pubmed_fallback(query_used)
                web_retrieval_ms = (time.perf_counter() - web_start) * 1000.0
                pubmed_docs_count = len(pubmed_docs)
                if attempt_logs:
                    attempt_logs[-1]["pubmed_web"] = {
                        "attempted": pubmed_attempted,
                        "docs": pubmed_docs_count,
                        "runtime_ms": web_retrieval_ms,
                    }
                if attempt_history:
                    attempt_history[-1]["pubmed_web"] = {
                        "attempted": pubmed_attempted,
                        "docs": pubmed_docs_count,
                        "runtime_ms": web_retrieval_ms,
                    }
                if pubmed_docs:
                    override_docs = pubmed_docs
                    override_reason = "pubmed_web_fallback"
                    override_retrieval_ms = web_retrieval_ms
                    attempt_reason = "pubmed_web_fallback"
                    extra_instructions = None
                    continue
            if question_result.status == "INSUFFICIENT_EVIDENCE" or (
                "missing_evidence" in selected_failed_checks
            ):
                evidence_top_k = expanded_top_k
                query_override = _rewrite_query(item.topic, item.competency)
                attempt_reason = "v3_insufficient"
                extra_instructions = None
                continue
            if "duplicate_question" in selected_failed_checks:
                extra_instructions = _merge_instructions(
                    _DEDUPLICATE_INSTRUCTION,
                    _EVIDENCE_FOCUS_INSTRUCTION,
                )
                attempt_reason = "v7_deduplicate"
                continue
            if llm_error in ("invalid_json", "short", "empty_response") or (
                "schema_validation" in selected_failed_checks
            ):
                extra_instructions = _STRICT_JSON_INSTRUCTION
                attempt_reason = "v4_json_strict"
                continue
            if any(check in _V2_FAILED_CHECKS for check in selected_failed_checks):
                extra_instructions = _REQUOTE_INSTRUCTION
                attempt_reason = "v2_requote"
                continue
            if any(
                check in ("reviewer_mismatch", "reviewer_insufficient")
                for check in selected_failed_checks
            ):
                extra_instructions = _EVIDENCE_FOCUS_INSTRUCTION
                attempt_reason = "v5_reviewer"
                continue
            if question_result.status != "OK":
                extra_instructions = _EVIDENCE_FOCUS_INSTRUCTION
                attempt_reason = "v6_retry"
                continue

        final_question = question_result
        final_evidence_doc_ids = evidence_doc_ids
        break

    if final_question is None:
        final_question = _build_failure_question(
            item,
            status="FAILED_VERIFICATION",
            error_message="pipeline_error",
        )

    if track_doc_ids and final_question.status == "OK" and final_evidence_doc_ids:
        doc_id_tracker.update(final_evidence_doc_ids)

    verification_meta = dict(final_question.meta.verification or {})
    verification_meta["attempt_history"] = attempt_history
    final_question.meta.verification = verification_meta

    return final_question, attempt_logs


def run_pipeline_stream(
    payload: List[GenerateRequestItem],
    include_failed: bool = True,
) -> Iterator[Dict[str, object]]:
    retriever = _get_retriever()
    llm_client = _get_llm_client()
    reviewer_client = _get_reviewer_client()
    run_started = time.perf_counter()
    run_id = uuid.uuid4().hex
    run_timestamp = datetime.utcnow().isoformat() + "Z"
    run_log_items: List[Dict[str, object]] = []
    input_batch = [item.model_dump() for item in payload]
    total_questions = sum(max(item.n_questions, 1) for item in payload)
    completed = 0
    run_used_stems: List[str] = []
    run_used_normalized = set()
    run_used_doc_ids = set()
    ok_only_mode = settings.OK_ONLY_MODE
    ok_only_max_rounds = max(settings.OK_ONLY_MAX_ROUNDS, 1)
    ok_only_max_seconds = max(settings.OK_ONLY_MAX_SECONDS, 0.0)
    bank_questions: List[QuestionItem] = []
    bank_normalized: set[str] = set()
    if ok_only_mode and (
        settings.QUESTION_BANK_FALLBACK or settings.QUESTION_BANK_WRITE_OK
    ):
        bank_questions = load_question_bank(settings.QUESTION_BANK_PATH)
        bank_normalized = {
            _normalize_stem(question.stem)
            for question in bank_questions
            if question.stem
        }

    yield {
        "type": "progress",
        "stage": "start",
        "run_id": run_id,
        "timestamp": run_timestamp,
        "total_questions": total_questions,
    }

    def build_question_event(
        question: QuestionItem, item_index: int, question_index: int
    ) -> Optional[Dict[str, object]]:
        if ok_only_mode:
            if question.status != "OK":
                return None
            return {
                "type": "question",
                "item_index": item_index,
                "question_index": question_index,
                "question": question.model_dump(),
            }
        if include_failed or question.status == "OK":
            return {
                "type": "question",
                "item_index": item_index,
                "question_index": question_index,
                "question": question.model_dump(),
            }
        return {
            "type": "question_failed",
            "item_index": item_index,
            "question_index": question_index,
            "status": question.status,
            "message": _summarize_failure_reason(question),
        }

    for item_index, item in enumerate(payload, start=1):
        item_attempts: List[Dict[str, object]] = []
        item_outputs: List[Dict[str, object]] = []
        item_reports: List[object] = []
        used_stems: List[str] = []

        try:
            if item.n_questions < 1:
                raise ValueError("n_questions must be >= 1")

            item_started = time.perf_counter()
            ok_only_deadline = None
            if ok_only_mode and ok_only_max_seconds > 0:
                ok_only_deadline = item_started + ok_only_max_seconds

            if retriever is None:
                if ok_only_mode:
                    pending_questions: List[QuestionItem] = []
                    pending_normalized: set[str] = set()
                    item_failed = False
                    if not settings.QUESTION_BANK_FALLBACK:
                        item_failed = True
                        remaining = item.n_questions
                        for _ in range(remaining):
                            failure_question = _build_failure_question(
                                item,
                                status="FAILED_VERIFICATION",
                                error_message=_GENERIC_FAILURE_MESSAGE,
                            )
                            item_outputs.append(failure_question.model_dump())
                            item_reports.append(
                                failure_question.meta.verification.get("gate")
                            )
                        yield {
                            "type": "error",
                            "item_index": item_index,
                            "message": _GENERIC_FAILURE_MESSAGE,
                        }
                    else:
                        for question_index in range(1, item.n_questions + 1):
                            avoid_normalized = set(run_used_normalized)
                            avoid_normalized.update(
                                _normalize_stem(stem) for stem in used_stems if stem
                            )
                            avoid_normalized.update(pending_normalized)
                            fallback_question = _select_bank_question(
                                bank_questions,
                                item.topic,
                                item.competency,
                                avoid_normalized,
                                settings.QUESTION_BANK_ALLOW_ANY_TOPIC,
                            )
                            if fallback_question is None:
                                item_failed = True
                                remaining = item.n_questions - question_index + 1
                                for _ in range(remaining):
                                    failure_question = _build_failure_question(
                                        item,
                                        status="FAILED_VERIFICATION",
                                        error_message=_GENERIC_FAILURE_MESSAGE,
                                    )
                                    item_outputs.append(failure_question.model_dump())
                                    item_reports.append(
                                        failure_question.meta.verification.get("gate")
                                    )
                                yield {
                                    "type": "error",
                                    "item_index": item_index,
                                    "message": _GENERIC_FAILURE_MESSAGE,
                                }
                                break
                            question = fallback_question
                            normalized_stem = _normalize_stem(question.stem or "")
                            item_outputs.append(question.model_dump())
                            item_reports.append(question.meta.verification.get("gate"))
                            pending_questions.append(question)
                            if question.stem and normalized_stem:
                                used_stems.append(question.stem)
                                pending_normalized.add(normalized_stem)
                    if item_failed:
                        continue

                    for question_index, question in enumerate(
                        pending_questions, start=1
                    ):
                        normalized_stem = _normalize_stem(question.stem or "")
                        if question.stem and normalized_stem:
                            run_used_stems.append(question.stem)
                            run_used_normalized.add(normalized_stem)
                        completed += 1
                        event = build_question_event(
                            question, item_index, question_index
                        )
                        if event is not None:
                            yield event
                        yield {
                            "type": "progress",
                            "completed": completed,
                            "total_questions": total_questions,
                        }
                    continue

                failure_questions = build_failure_batch(
                    [item], "retriever_unavailable"
                )
                for question_index, question in enumerate(failure_questions, start=1):
                    item_outputs.append(question.model_dump())
                    item_reports.append(question.meta.verification.get("gate"))
                    completed += 1
                    event = build_question_event(question, item_index, question_index)
                    if event is not None:
                        yield event
                    yield {
                        "type": "progress",
                        "completed": completed,
                        "total_questions": total_questions,
                    }
                continue

            if ok_only_mode:
                item_doc_ids: set[str] = set()
                item_failed = False
                for question_index in range(1, item.n_questions + 1):
                    question = None
                    normalized_stem = ""
                    local_attempt_stems: List[str] = []
                    ok_round = 0
                    while True:
                        ok_round += 1
                        if ok_only_deadline is not None:
                            if time.perf_counter() > ok_only_deadline:
                                break
                        for dedup_attempt in range(1, _MAX_DEDUP_ATTEMPTS + 1):
                            avoid_stems = (
                                used_stems + run_used_stems + local_attempt_stems
                            )
                            question, attempt_logs = _generate_single_question(
                                item,
                                retriever,
                                llm_client,
                                reviewer_client,
                                avoid_stems,
                                item_doc_ids,
                            )
                            for log in attempt_logs:
                                log["question_index"] = question_index
                                log["dedup_attempt"] = dedup_attempt
                                log["ok_round"] = ok_round
                                item_attempts.append(log)
                            if question.stem:
                                local_attempt_stems.append(question.stem)
                            normalized_stem = _normalize_stem(question.stem or "")
                            if normalized_stem and (
                                normalized_stem in run_used_normalized
                            ):
                                verification_meta = dict(
                                    question.meta.verification or {}
                                )
                                verification_meta.setdefault(
                                    "error", "duplicate_question"
                                )
                                verification_meta["duplicate"] = True
                                verification_meta["dedup_attempt"] = dedup_attempt
                                question.meta.verification = verification_meta
                                question.status = "FAILED_VERIFICATION"
                                if dedup_attempt < _MAX_DEDUP_ATTEMPTS:
                                    continue
                            break
                        if question is None:
                            break
                        if question.status == "OK":
                            break
                        time_exceeded = False
                        if ok_only_deadline is not None:
                            time_exceeded = time.perf_counter() > ok_only_deadline
                        if ok_round < ok_only_max_rounds and not time_exceeded:
                            continue
                        break

                    if question is None or question.status != "OK":
                        fallback_question = None
                        if settings.QUESTION_BANK_FALLBACK:
                            avoid_normalized = set(run_used_normalized)
                            avoid_normalized.update(
                                _normalize_stem(stem) for stem in used_stems if stem
                            )
                            fallback_question = _select_bank_question(
                                bank_questions,
                                item.topic,
                                item.competency,
                                avoid_normalized,
                                settings.QUESTION_BANK_ALLOW_ANY_TOPIC,
                            )
                        if fallback_question is not None:
                            question = fallback_question
                            normalized_stem = _normalize_stem(question.stem or "")
                        else:
                            item_failed = True
                            remaining = item.n_questions - question_index + 1
                            for _ in range(remaining):
                                failure_question = _build_failure_question(
                                    item,
                                    status="FAILED_VERIFICATION",
                                    error_message=_GENERIC_FAILURE_MESSAGE,
                                )
                                item_outputs.append(failure_question.model_dump())
                                item_reports.append(
                                    failure_question.meta.verification.get("gate")
                                )
                            yield {
                                "type": "error",
                                "item_index": item_index,
                                "message": _GENERIC_FAILURE_MESSAGE,
                            }
                            break

                    item_outputs.append(question.model_dump())
                    item_reports.append(question.meta.verification.get("gate"))
                    if question.stem and normalized_stem:
                        used_stems.append(question.stem)
                        run_used_stems.append(question.stem)
                        run_used_normalized.add(normalized_stem)
                    if (
                        question.status == "OK"
                        and settings.QUESTION_BANK_WRITE_OK
                        and normalized_stem
                        and normalized_stem not in bank_normalized
                    ):
                        append_question_bank(settings.QUESTION_BANK_PATH, question)
                        bank_questions.append(question)
                        bank_normalized.add(normalized_stem)

                    completed += 1
                    event = build_question_event(
                        question, item_index, question_index
                    )
                    if event is not None:
                        yield event
                    yield {
                        "type": "progress",
                        "completed": completed,
                        "total_questions": total_questions,
                    }

                if item_failed:
                    continue

                if item_doc_ids:
                    run_used_doc_ids.update(item_doc_ids)
                continue

            for question_index in range(1, item.n_questions + 1):
                question = None
                normalized_stem = ""
                for dedup_attempt in range(1, _MAX_DEDUP_ATTEMPTS + 1):
                    avoid_stems = used_stems + run_used_stems
                    question, attempt_logs = _generate_single_question(
                        item,
                        retriever,
                        llm_client,
                        reviewer_client,
                        avoid_stems,
                        run_used_doc_ids,
                    )
                    for log in attempt_logs:
                        log["question_index"] = question_index
                        log["dedup_attempt"] = dedup_attempt
                        item_attempts.append(log)
                    normalized_stem = _normalize_stem(question.stem or "")
                    if normalized_stem and normalized_stem in run_used_normalized:
                        verification_meta = dict(question.meta.verification or {})
                        verification_meta.setdefault("error", "duplicate_question")
                        verification_meta["duplicate"] = True
                        verification_meta["dedup_attempt"] = dedup_attempt
                        question.meta.verification = verification_meta
                        question.status = "FAILED_VERIFICATION"
                        if dedup_attempt < _MAX_DEDUP_ATTEMPTS:
                            continue
                    break

                if question is None:
                    question = _build_failure_question(
                        item,
                        status="FAILED_VERIFICATION",
                        error_message="pipeline_error",
                    )
                    normalized_stem = ""

                item_outputs.append(question.model_dump())
                item_reports.append(question.meta.verification.get("gate"))
                if question.stem and normalized_stem not in run_used_normalized:
                    used_stems.append(question.stem)
                    run_used_stems.append(question.stem)
                    run_used_normalized.add(normalized_stem)
                completed += 1
                event = build_question_event(question, item_index, question_index)
                if event is not None:
                    yield event
                yield {
                    "type": "progress",
                    "completed": completed,
                    "total_questions": total_questions,
                }
                if (
                    question.status == "OK"
                    and settings.QUESTION_BANK_WRITE_OK
                    and normalized_stem
                    and normalized_stem not in bank_normalized
                ):
                    append_question_bank(settings.QUESTION_BANK_PATH, question)
                    bank_questions.append(question)
                    bank_normalized.add(normalized_stem)
        except ValueError as exc:
            failure_questions = build_failure_batch(
                [item], str(exc), status="FAILED_VERIFICATION"
            )
            yield {
                "type": "error",
                "item_index": item_index,
                "message": _GENERIC_FAILURE_MESSAGE if ok_only_mode else str(exc),
            }
            for question_index, question in enumerate(failure_questions, start=1):
                item_outputs.append(question.model_dump())
                item_reports.append(question.meta.verification.get("gate"))
                if not ok_only_mode:
                    completed += 1
                    event = build_question_event(
                        question, item_index, question_index
                    )
                    if event is not None:
                        yield event
                    yield {
                        "type": "progress",
                        "completed": completed,
                        "total_questions": total_questions,
                    }
        except Exception as exc:
            failure_questions = build_failure_batch(
                [item], f"pipeline_error: {exc}", status="FAILED_VERIFICATION"
            )
            yield {
                "type": "error",
                "item_index": item_index,
                "message": _GENERIC_FAILURE_MESSAGE
                if ok_only_mode
                else f"pipeline_error: {exc}",
            }
            for question_index, question in enumerate(failure_questions, start=1):
                item_outputs.append(question.model_dump())
                item_reports.append(question.meta.verification.get("gate"))
                if not ok_only_mode:
                    completed += 1
                    event = build_question_event(
                        question, item_index, question_index
                    )
                    if event is not None:
                        yield event
                    yield {
                        "type": "progress",
                        "completed": completed,
                        "total_questions": total_questions,
                    }
        finally:
            run_log_items.append(
                {
                    "input": item.model_dump(),
                    "attempts": item_attempts,
                    "outputs": item_outputs,
                    "verification_reports": item_reports,
                }
            )

    run_record = {
        "run_id": run_id,
        "timestamp": run_timestamp,
        "input_batch": input_batch,
        "items": run_log_items,
        "runtime_ms": (time.perf_counter() - run_started) * 1000.0,
    }
    summary: Optional[Dict[str, object]] = None
    try:
        summary = log_run(run_record)
    except Exception as exc:
        LOGGER.warning("Failed to log run: %s", exc)

    summary_out = None if ok_only_mode else summary

    yield {
        "type": "done",
        "run_id": run_id,
        "completed": completed,
        "total_questions": total_questions,
        "summary": summary_out,
    }


def run_pipeline_batch(payload: List[GenerateRequestItem]) -> List[QuestionItem]:
    results: List[QuestionItem] = []
    saw_error = False
    for event in run_pipeline_stream(payload):
        if event.get("type") == "question":
            results.append(QuestionItem.model_validate(event["question"]))
        if event.get("type") == "error" and settings.OK_ONLY_MODE:
            saw_error = True
    if saw_error and settings.OK_ONLY_MODE:
        return []
    return results
