"""Reviewer client factories for CoVe verification."""
from __future__ import annotations

import logging
from typing import List, Optional

from app.core.config import settings
from app.generation.llm_client import LLMClient
from app.verification.gate import CrossCoVeReviewer, ReviewerClient

LOGGER = logging.getLogger(__name__)


def _create_reviewer_from_config(
    provider: str,
    api_key: str,
    model: str,
    fallbacks_json: str = "",
    api_base: str = "",
) -> Optional[ReviewerClient]:
    if not model or not provider:
        return None

    timeout_sec = settings.REVIEWER_TIMEOUT_SEC or settings.LLM_TIMEOUT_SEC
    cerebras_api_key = ""
    groq_api_key = ""
    provider_lower = provider.strip().lower()

    if provider_lower in ("cerebras", "cerebras_sdk", "cerebras_cloud"):
        cerebras_api_key = api_key
    elif provider_lower in ("groq", "groq_sdk", "groq_cloud"):
        groq_api_key = api_key

    try:
        llm_client = LLMClient(
            api_key=api_key or None,
            api_base=api_base or None,
            model=model,
            timeout_sec=timeout_sec,
            provider=provider_lower or None,
            groq_api_key=groq_api_key or None,
            cerebras_api_key=cerebras_api_key or None,
            fallback_targets_json=fallbacks_json,
            max_completion_tokens=settings.REVIEWER_MAX_COMPLETION_TOKENS,
        )
        return ReviewerClient(llm_client, model_name=model)
    except Exception as exc:
        LOGGER.warning("Failed to create reviewer for model %s: %s", model, exc)
        return None


def _get_reviewer_client() -> Optional[ReviewerClient]:
    provider = (settings.REVIEWER_PROVIDER or settings.LLM_PROVIDER or "").strip().lower()
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
        max_completion_tokens=settings.REVIEWER_MAX_COMPLETION_TOKENS,
    )
    return ReviewerClient(reviewer_llm, model_name=model)


def _get_cross_cove_reviewer() -> Optional[CrossCoVeReviewer]:
    if not settings.COVE_ENABLED:
        return None

    reviewers: List[ReviewerClient] = []

    for provider_key, api_key_key, model_key, fallbacks_key, base_key in [
        (
            settings.REVIEWER_1_PROVIDER or settings.REVIEWER_PROVIDER,
            settings.REVIEWER_1_API_KEY or settings.REVIEWER_API_KEY,
            settings.REVIEWER_1_MODEL or settings.REVIEWER_MODEL,
            settings.REVIEWER_1_FALLBACKS,
            settings.REVIEWER_1_API_BASE or settings.REVIEWER_API_BASE or "",
        ),
        (
            settings.REVIEWER_2_PROVIDER or settings.REVIEWER_PROVIDER,
            settings.REVIEWER_2_API_KEY or settings.REVIEWER_API_KEY,
            settings.REVIEWER_2_MODEL,
            settings.REVIEWER_2_FALLBACKS,
            settings.REVIEWER_2_API_BASE or settings.REVIEWER_API_BASE or "",
        ),
        (
            settings.REVIEWER_3_PROVIDER or settings.REVIEWER_PROVIDER,
            settings.REVIEWER_3_API_KEY or settings.REVIEWER_API_KEY,
            settings.REVIEWER_3_MODEL,
            settings.REVIEWER_3_FALLBACKS,
            settings.REVIEWER_3_API_BASE or settings.REVIEWER_API_BASE or "",
        ),
    ]:
        r = _create_reviewer_from_config(provider_key, api_key_key, model_key, fallbacks_key, api_base=base_key)
        if r:
            reviewers.append(r)

    if len(reviewers) < 2:
        LOGGER.warning(
            "Cross-CoVe requires at least 2 reviewers, got %d. Falling back to single reviewer.",
            len(reviewers),
        )
        return None

    LOGGER.info(
        "Cross-CoVe initialized with %d reviewers: %s",
        len(reviewers),
        [r._model_name for r in reviewers],
    )
    return CrossCoVeReviewer(reviewers)
