from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from pydantic import TypeAdapter, ValidationError

from app.core.config import settings
from app.schemas.response import Meta, Options, QuestionItem
from app.generation.prompt_templates import build_prompt

LOGGER = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
    ) -> None:
        self._api_key = api_key or settings.LLM_API_KEY
        self._api_base = api_base or settings.LLM_API_BASE
        self._model = model or settings.LLM_MODEL
        self._timeout_sec = timeout_sec or settings.LLM_TIMEOUT_SEC

    def generate_mcq(
        self,
        topic: str,
        competency: str,
        evidence_text: str,
        n_questions: int,
    ) -> List[QuestionItem]:
        prompt = build_prompt(topic, competency, evidence_text, n_questions)
        content = self._chat_completion(prompt)
        if content is None:
            return self._fallback_items(topic, competency, n_questions, "empty_response")

        try:
            data = _parse_json_response(content)
            adapter = TypeAdapter(List[QuestionItem])
            items = adapter.validate_python(data)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.warning("Failed to parse LLM JSON: %s", exc)
            return self._fallback_items(topic, competency, n_questions, "invalid_json")

        if len(items) < n_questions:
            items.extend(self._fallback_items(topic, competency, n_questions - len(items), "short"))
        if len(items) > n_questions:
            items = items[:n_questions]
        return items

    def _chat_completion(self, prompt: str) -> Optional[str]:
        if not self._api_key:
            LOGGER.error("LLM_API_KEY is not set")
            return None
        if not self._model:
            LOGGER.error("LLM_MODEL is not set")
            return None

        try:
            from google import genai
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.error("google-genai is not installed: %s", exc)
            return None

        try:
            client = genai.Client(api_key=self._api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"temperature": 0.2},
            )
        except Exception as exc:
            LOGGER.error("LLM request failed: %s", exc)
            return None

        text = getattr(response, "text", None)
        if text:
            return text

        try:
            candidates = getattr(response, "candidates", None) or []
            if not candidates:
                raise ValueError("empty_candidates")
            content = candidates[0].content
            parts = getattr(content, "parts", None) or []
            texts = [getattr(part, "text", "") for part in parts]
            combined = "".join(texts).strip()
            return combined or None
        except Exception:
            LOGGER.error("LLM response missing content")
            return None

    def _fallback_items(
        self, topic: str, competency: str, n_questions: int, reason: str
    ) -> List[QuestionItem]:
        items: List[QuestionItem] = []
        for _ in range(max(n_questions, 0)):
            items.append(
                QuestionItem(
                    topic=topic,
                    competency=competency,
                    stem="",
                    options=Options(A="", B="", C="", D=""),
                    answer_key="A",
                    explanation=reason,
                    evidence=[],
                    status="FAILED_VERIFICATION",
                    meta=Meta(
                        retrieval={"error": reason},
                        verification={"error": reason},
                        timings_ms={},
                    ),
                )
            )
        return items


def _strip_code_fences(text: str) -> str:
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_json_block(text: str) -> str:
    text = _strip_code_fences(text)
    if "[" in text and "]" in text:
        start = text.find("[")
        end = text.rfind("]")
        return text[start : end + 1]
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        return text[start : end + 1]
    return text


def _repair_json(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _parse_json_response(content: str) -> Any:
    raw = _extract_json_block(content)
    raw = _repair_json(raw)
    data = json.loads(raw)
    if isinstance(data, dict):
        return [data]
    return data
