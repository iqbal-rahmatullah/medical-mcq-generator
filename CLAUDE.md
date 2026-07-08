# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

FastAPI-based system for generating medical multiple-choice questions (MCQs) using retrieval-augmented generation (RAG). The backend retrieves evidence from a PubMed/textbook corpus, generates questions with an LLM, and verifies grounding before logging results. A Next.js frontend streams questions over WebSocket and provides a UI for configuring topics and reviewing outputs.

## Commands

Backend (Python, in `.venv`, requires Python >=3.10):
```bash
source .venv/bin/activate
uvicorn app.main:app --reload           # run API on :8000
pytest                                    # run all tests
pytest tests/test_retriever.py           # run one test file
pytest tests/test_bm25.py::test_name -v  # run a single test
```

Frontend (`web/`, Next.js 14 + React 18 + TypeScript):
```bash
cd web
npm run dev     # dev server (expects API at NEXT_PUBLIC_API_BASE_URL, default http://localhost:8000)
npm run build
npm run lint
```

There is no Makefile, linter config, or CI test command beyond `pytest`/`next lint` — use those directly.

## Architecture

### Request flow

`web/` (Next.js) → WebSocket `/ws/generate` (or REST `POST /generate`) in `app/api/routes.py` → `app/services/pipeline.py::run_pipeline_stream` orchestrates the whole generation loop and yields progress/question/error/done events, which the WS route forwards to the client in real time. `run_pipeline_batch` drains the same stream for the synchronous REST path.

### Pipeline internals (`app/services/`)

- `pipeline.py` — top-level orchestration per batch item: retriever/LLM/reviewer singletons, retriever disk cache (dev-only, fingerprinted by corpus/BM25 config), the "OK-only" retry loop (keeps regenerating until a question passes verification or budgets run out), question-bank fallback/backfill, and run logging.
- `_question_generator.py` — `_generate_single_question`: the retrieve → prompt → verify → retry loop for one question. Tracks attempt reasons (`v2_requote`, `v3_insufficient`, `v4_json_strict`, `v5_reviewer`, `v6_retry`, `v7_deduplicate`, `v8_evidence_diversity`, `pubmed_web_fallback`) that each mutate retrieval params or prompt instructions before retrying. Falls back to live PubMed web fetch (`app/retrieval/pubmed_web.py`) when the local corpus retrieval or reviewer coverage check comes back empty.
- `_reviewers.py` — builds `ReviewerClient`/`CrossCoVeReviewer` instances from `REVIEWER_*` / `REVIEWER_{1,2,3}_*` settings.
- `_pipeline_utils.py` — shared helpers (failure question construction, stem normalization/hashing for dedup, question-bank selection, log truncation).

Two important run modes controlled by settings:
- `OK_ONLY_MODE` (default true): only `status == "OK"` questions are ever emitted; the pipeline keeps retrying/falling back until it produces one or exhausts `OK_ONLY_MAX_ROUNDS`/`OK_ONLY_MAX_SECONDS`, then falls back to the question bank or a "graceful fallback" (best-effort question marked OK).
- `QUESTION_BANK_FALLBACK` / `QUESTION_BANK_WRITE_OK`: the question bank (`app/logging/question_bank.py`, JSONL at `QUESTION_BANK_PATH`) is both a source of fallback questions when generation fails and a sink for newly generated OK questions, deduped by normalized stem.

### Retrieval (`app/retrieval/`, `app/corpus/`)

- `DocumentStore` (`corpus/store.py`) loads docs via `corpus/loaders.py` from HF datasets (`MedRAG/pubmed`, `MedRAG/textbooks`), capped by `CORPUS_*_MAX_DOCS`.
- `BM25Index` (`retrieval/bm25.py`) is built once per process and cached to disk (`RETRIEVER_CACHE_PATH`) in dev environments, keyed by a fingerprint of corpus/BM25 settings.
- `Retriever.retrieve()` (`retrieval/retriever.py`) runs BM25 → optional MedCPT dense rerank (`RETRIEVAL_MODE=hybrid_rerank`) → optional RRF fusion (`FUSION_ENABLED`) → topic-token filtering → evidence slice (`EVIDENCE_TOP_K`). `pubmed_web.py` is the live fallback when local retrieval is empty.

### Generation (`app/generation/`)

- `llm_client.py` — `LLMClient` abstracts multiple providers (`gemini_sdk`, `openai_compatible`, `groq`, `cerebras`, `ollama`) selected via `LLM_PROVIDER`, with fallback target chains (`LLM_FALLBACKS` JSON) and JSON-mode MCQ parsing (`generate_mcq`) plus plain text (`generate_text`, used by reviewers).
- `prompt_templates.py` — builds the MCQ generation prompt (topic, competency, evidence, extra instructions, language).
- `evidence_format.py` — extracts/trims evidence spans for prompts (`EVIDENCE_FIRST*` settings) and renders evidence blocks (char-capped per doc and total).

### Verification (`app/verification/gate.py`)

`verify_questions()` runs a battery of checks per generated question: schema validation, evidence span presence/fuzzy match against source docs, LLM-based topic coverage (non-blocking, notes only) and topic relevance (blocking), forbidden option formats ("all/none of the above"), and clinical-vignette-vs-definitional stem detection via regex. If all checks pass, a reviewer verifies the answer is derivable from evidence — either a single `ReviewerClient` or `CrossCoVeReviewer`, which runs 3 independently configured reviewer LLMs (`REVIEWER_1/2/3_*` settings) in parallel and takes a majority vote (`COVE_ENABLED`, `COVE_VOTE_COUNT`). Failing questions get their `status` downgraded (`INSUFFICIENT_EVIDENCE` for topic coverage failures, `FAILED_VERIFICATION` otherwise) and failure detail attached to `meta.verification.gate`.

### Config (`app/core/config.py`)

Single `pydantic-settings` `Settings` object loaded from `.env`. Every tunable (retrieval mode/params, LLM provider/model/timeouts, OK-only budgets, evidence trimming, reviewer/Cross-CoVe provider chains, corpus dataset names, PubMed web fallback, NLI/semantic eval model names) lives here — check this file first when tracing behavior driven by env vars. See `.env.example` for the full documented list and provider-specific examples (Gemini, OpenAI-compatible/Groq, Ollama).

### Evaluation (`app/eval/`)

Offline quality metrics computed over the question bank JSONL, exposed via `/eval/rouge`, `/eval/nli`, `/eval/semantic` routes and `app/scripts/evaluate_quality_metrics.py`: ROUGE (stem+answer vs evidence), NLI entailment (`NLI_MODEL`), and embedding cosine similarity (`SEMANTIC_MODEL`). `app/eval/ablation.py` supports Cross-CoVe on/off ablation studies (see `app/scripts/analyze_cove_ablation.py`, `data/ablation_cove_*.jsonl`).

### Frontend (`web/`)

- `app/hooks/useQuestionGenerator.ts` owns the WebSocket lifecycle for `/ws/generate`, streaming `progress`/`question`/`question_failed`/`error`/`done` events into UI state, and writes completed runs to browser history (`app/lib/history.ts`).
- `app/lib/config.ts` derives `API_BASE`/`WS_BASE` from `NEXT_PUBLIC_API_BASE_URL` (falls back to `localhost:8000`, and derives the WS URL from it if `NEXT_PUBLIC_WS_BASE_URL` isn't set).
- `app/lib/export.ts` handles exporting question sets (docx/pdf via `docx`/`jspdf`).
- `app/history/` — persisted run history list + detail view; `app/docs/` — static docs page.

## Notes

- `app/logging/` contains both the per-run structured logger (`logger.py`, `latency_logger.py`) and the question bank persistence (`question_bank.py`) — don't confuse "logging" here with Python's `logging` module usage elsewhere.
- The retriever/LLM singletons in `pipeline.py` are process-global and lazily initialized; the BM25 disk cache is only read/written when `environment` is `local`/`development`/`dev`.
