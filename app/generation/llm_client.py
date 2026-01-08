from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, List, Optional

from pydantic import TypeAdapter, ValidationError

from app.core.config import settings
from app.schemas.response import Meta, Options, QuestionItem
from app.generation.prompt_templates import build_prompt

LOGGER = logging.getLogger(__name__)

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_OLLAMA_DEFAULT_BASE = "http://localhost:11434"
_RAW_LOG_LIMIT = 4000


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        timeout_sec: Optional[float] = None,
        provider: Optional[str] = None,
        groq_api_key: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or settings.LLM_API_KEY
        self._api_base = api_base or settings.LLM_API_BASE
        self._model = model or settings.LLM_MODEL
        self._timeout_sec = timeout_sec or settings.LLM_TIMEOUT_SEC
        self._provider = (provider or settings.LLM_PROVIDER or "").strip().lower()
        self._groq_api_key = (groq_api_key or settings.GROQ_API_KEY or "").strip()
        self._temperature = settings.LLM_TEMPERATURE
        self._top_p = settings.LLM_TOP_P
        self._max_completion_tokens = settings.LLM_MAX_COMPLETION_TOKENS
        self._reasoning_effort = settings.LLM_REASONING_EFFORT.strip()
        self._stop = settings.LLM_STOP.strip()
        self._stream = settings.LLM_STREAM

    def generate_mcq(
        self,
        topic: str,
        competency: str,
        evidence_text: str,
        n_questions: int,
        extra_instructions: Optional[str] = None,
    ) -> List[QuestionItem]:
        prompt = build_prompt(
            topic,
            competency,
            evidence_text,
            n_questions,
            extra_instructions=extra_instructions,
        )
        content = self._chat_completion(prompt)
        if content is None:
            return self._fallback_items(topic, competency, n_questions, "empty_response")

        try:
            data = _parse_json_response(content)
            adapter = TypeAdapter(List[QuestionItem])
            items = adapter.validate_python(data)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            raw = content if isinstance(content, str) else str(content)
            if len(raw) > _RAW_LOG_LIMIT:
                raw = f"{raw[:_RAW_LOG_LIMIT]}...(truncated)"
            LOGGER.warning("LLM raw response: %s", raw)
            LOGGER.warning("Failed to parse LLM JSON: %s", exc)
            return self._fallback_items(topic, competency, n_questions, "invalid_json")

        if len(items) < n_questions:
            items.extend(self._fallback_items(topic, competency, n_questions - len(items), "short"))
        if len(items) > n_questions:
            items = items[:n_questions]
        return items

    def generate_text(self, prompt: str) -> Optional[str]:
        return self._chat_completion(prompt)

    def _chat_completion(self, prompt: str) -> Optional[str]:
        if not self._model:
            LOGGER.error("LLM_MODEL is not set")
            return None

        provider = self._provider or "gemini_sdk"
        if provider in ("ollama",):
            return self._ollama_generate(prompt)

        if provider in ("groq", "groq_sdk", "groq_cloud"):
            return self._groq_generate(prompt)

        if provider in ("gemini_sdk", "gemini", "google_genai"):
            if not self._api_key:
                LOGGER.error("LLM_API_KEY is not set")
                return None
            return self._gemini_generate(prompt)
        if provider in ("openai_compatible", "openai"):
            if not self._api_key:
                LOGGER.error("LLM_API_KEY is not set")
                return None
            return self._openai_compatible_generate(prompt)

        LOGGER.error("Unsupported LLM_PROVIDER: %s", provider)
        return None

    def _gemini_generate(self, prompt: str) -> Optional[str]:
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
                config={"temperature": self._temperature},
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

    def _openai_compatible_generate(self, prompt: str) -> Optional[str]:
        if not self._api_base:
            LOGGER.error("LLM_API_BASE is not set")
            return None

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "You are a helpful medical QA generator."},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "top_p": self._top_p,
            "max_completion_tokens": self._max_completion_tokens,
            "stream": self._stream,
        }
        if self._reasoning_effort:
            payload["reasoning_effort"] = self._reasoning_effort
        if self._stop:
            payload["stop"] = [s.strip() for s in self._stop.split(",") if s.strip()]
        else:
            payload["stop"] = None

        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        request = urllib.request.Request(
            self._api_base, data=body, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            LOGGER.error("LLM HTTP error: %s", exc)
            return None
        except urllib.error.URLError as exc:
            LOGGER.error("LLM connection error: %s", exc)
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.error("LLM response not JSON")
            return None

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            LOGGER.error("LLM response missing content")
            return None

    def _groq_generate(self, prompt: str) -> Optional[str]:
        try:
            from groq import Groq
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.error("groq is not installed: %s", exc)
            return None

        api_key = self._groq_api_key or self._api_key
        if not api_key:
            LOGGER.error("GROQ_API_KEY is not set")
            return None

        try:
            client = Groq(api_key=api_key)
            payload: dict[str, Any] = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": "You are a helpful medical QA generator."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": self._temperature,
                "top_p": self._top_p,
                "max_completion_tokens": self._max_completion_tokens,
            }
            if self._stop:
                payload["stop"] = [s.strip() for s in self._stop.split(",") if s.strip()]
            response = client.chat.completions.create(**payload)
        except Exception as exc:
            LOGGER.error("LLM request failed: %s", exc)
            return None

        try:
            return response.choices[0].message.content
        except Exception:
            LOGGER.error("LLM response missing content")
            return None

    def _ollama_generate(self, prompt: str) -> Optional[str]:
        base = self._api_base.strip() if self._api_base else _OLLAMA_DEFAULT_BASE
        url = _build_ollama_url(base)
        options: dict[str, Any] = {
            "temperature": self._temperature,
            "top_p": self._top_p,
        }
        if self._max_completion_tokens > 0:
            options["num_predict"] = self._max_completion_tokens
        if self._stop:
            options["stop"] = [s.strip() for s in self._stop.split(",") if s.strip()]

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "You are a helpful medical QA generator."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": options,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
        }
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            LOGGER.error("LLM HTTP error: %s", exc)
            return None
        except urllib.error.URLError as exc:
            LOGGER.error("LLM connection error: %s", exc)
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.error("LLM response not JSON")
            return None

        message = data.get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        response_text = data.get("response")
        if isinstance(response_text, str) and response_text.strip():
            return response_text.strip()

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


def _build_ollama_url(api_base: str) -> str:
    base = api_base.strip().rstrip("/")
    if base.endswith("/api/chat") or base.endswith("/api/generate"):
        return base
    return f"{base}/api/chat"
