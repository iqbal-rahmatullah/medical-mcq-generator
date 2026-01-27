from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

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
        cerebras_api_key: Optional[str] = None,
        fallback_targets_json: Optional[str] = None,
    ) -> None:
        self._api_key = api_key or settings.LLM_API_KEY
        self._api_base = api_base or settings.LLM_API_BASE
        self._model = model or settings.LLM_MODEL
        self._timeout_sec = timeout_sec or settings.LLM_TIMEOUT_SEC
        self._provider = (provider or settings.LLM_PROVIDER or "").strip().lower()
        self._groq_api_key = (groq_api_key or settings.GROQ_API_KEY or "").strip()
        self._cerebras_api_key = (
            cerebras_api_key or settings.CEREBRAS_API_KEY or ""
        ).strip()
        self._temperature = settings.LLM_TEMPERATURE
        self._top_p = settings.LLM_TOP_P
        self._max_completion_tokens = settings.LLM_MAX_COMPLETION_TOKENS
        self._reasoning_effort = settings.LLM_REASONING_EFFORT.strip()
        self._stop = settings.LLM_STOP.strip()
        self._stream = settings.LLM_STREAM
        self._fallback_targets = _parse_fallbacks(
            settings.LLM_FALLBACKS if fallback_targets_json is None else fallback_targets_json
        )
        self._last_error_kind = ""
        self._target_offset = 0

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
            fixed_items = None
            if isinstance(exc, ValidationError) and _needs_answer_key_fix(exc):
                repaired = self._repair_answer_key_with_llm(content, n_questions)
                if repaired:
                    try:
                        repaired_data = _parse_json_response(repaired)
                        adapter = TypeAdapter(List[QuestionItem])
                        fixed_items = adapter.validate_python(repaired_data)
                    except (ValidationError, ValueError, json.JSONDecodeError):
                        fixed_items = None

            if fixed_items is not None:
                items = fixed_items
            else:
                raw = content if isinstance(content, str) else str(content)
                if len(raw) > _RAW_LOG_LIMIT:
                    raw = f"{raw[:_RAW_LOG_LIMIT]}...(truncated)"
                LOGGER.warning("LLM raw response: %s", raw)
                LOGGER.warning("Failed to parse LLM JSON: %s", exc)
                return self._fallback_items(
                    topic, competency, n_questions, "invalid_json"
                )

        if len(items) < n_questions:
            items.extend(self._fallback_items(topic, competency, n_questions - len(items), "short"))
        if len(items) > n_questions:
            items = items[:n_questions]
        return items

    def _repair_answer_key_with_llm(
        self, raw_response: str, n_questions: int
    ) -> Optional[str]:
        if not raw_response or not raw_response.strip():
            return None
        prompt = (
            "You are fixing JSON for a medical MCQ schema.\n"
            "Task: Fix only answer_key values so each is a single letter: A, B, C, or D.\n"
            "If answer_key is a pattern like \"A|B|C|D\", infer the correct letter from the "
            "explanation or options; if unclear, use \"A\".\n"
            f"Return ONLY a JSON array of length {n_questions}. Do not add commentary.\n\n"
            "Input JSON:\n"
            f"{raw_response}"
        )
        return self._chat_completion(prompt)

    def generate_text(self, prompt: str) -> Optional[str]:
        return self._chat_completion(prompt)

    def _chat_completion(self, prompt: str) -> Optional[str]:
        if not self._model:
            LOGGER.error("LLM_MODEL is not set")
            self._last_error_kind = "config_error"
            return None

        targets = self._build_targets()
        if not targets:
            return None
        start_index = self._target_offset % len(targets)
        for step in range(len(targets)):
            index = (start_index + step) % len(targets)
            target = targets[index]
            content = self._dispatch_completion(prompt, target)
            if content is None:
                LOGGER.warning(
                    "LLM request failed: provider=%s model=%s key=%s kind=%s",
                    target.get("provider"),
                    target.get("model"),
                    _mask_key(
                        _select_log_key(
                            target.get("provider"),
                            target.get("api_key"),
                            target.get("groq_api_key"),
                            target.get("cerebras_api_key"),
                        )
                    ),
                    self._last_error_kind or "unknown",
                )
            if content:
                LOGGER.info(
                    "LLM request success: provider=%s model=%s key=%s",
                    target.get("provider"),
                    target.get("model"),
                    _mask_key(
                        _select_log_key(
                            target.get("provider"),
                            target.get("api_key"),
                            target.get("groq_api_key"),
                            target.get("cerebras_api_key"),
                        )
                    ),
                )
                self._target_offset = index
                return content
            if self._last_error_kind != "rate_limit":
                return None
            next_index = (index + 1) % len(targets)
            self._target_offset = next_index
            if step < len(targets) - 1:
                next_target = targets[next_index]
                LOGGER.warning(
                    "Rate limited; falling back from provider=%s model=%s key=%s to provider=%s model=%s key=%s",
                    target.get("provider"),
                    target.get("model"),
                    _mask_key(
                        _select_log_key(
                            target.get("provider"),
                            target.get("api_key"),
                            target.get("groq_api_key"),
                            target.get("cerebras_api_key"),
                        )
                    ),
                    next_target.get("provider"),
                    next_target.get("model"),
                    _mask_key(
                        _select_log_key(
                            next_target.get("provider"),
                            next_target.get("api_key"),
                            next_target.get("groq_api_key"),
                            next_target.get("cerebras_api_key"),
                        )
                    ),
                )
        return None

    def _build_targets(self) -> List[Dict[str, Optional[str]]]:
        primary = {
            "provider": (self._provider or "gemini_sdk").strip().lower(),
            "model": self._model,
            "api_key": self._api_key,
            "api_base": self._api_base,
            "groq_api_key": self._groq_api_key,
            "cerebras_api_key": self._cerebras_api_key,
        }
        targets = [primary]
        for entry in self._fallback_targets:
            provider = (entry.get("provider") or primary["provider"] or "").strip().lower()
            model = entry.get("model") or primary["model"]
            api_base = entry.get("api_base") or primary["api_base"]
            api_key = entry.get("api_key") or primary["api_key"]
            targets.append(
                {
                    "provider": provider,
                    "model": model,
                    "api_key": api_key,
                    "api_base": api_base,
                    "groq_api_key": entry.get("groq_api_key") or primary["groq_api_key"],
                    "cerebras_api_key": entry.get("cerebras_api_key") or primary["cerebras_api_key"],
                }
            )
        return targets

    def _dispatch_completion(
        self, prompt: str, target: Dict[str, Optional[str]]
    ) -> Optional[str]:
        provider = (target.get("provider") or "").strip().lower()
        model = target.get("model") or ""
        api_key = target.get("api_key") or ""
        api_base = target.get("api_base") or ""
        groq_api_key = target.get("groq_api_key") or ""
        cerebras_api_key = target.get("cerebras_api_key") or ""
        self._last_error_kind = ""
        LOGGER.info(
            "LLM request start: provider=%s model=%s key=%s",
            provider,
            model,
            _mask_key(_select_log_key(provider, api_key, groq_api_key, cerebras_api_key)),
        )

        if provider in ("ollama",):
            return self._ollama_generate(prompt, model=model, api_base=api_base)

        if provider in ("groq", "groq_sdk", "groq_cloud"):
            return self._groq_generate(
                prompt, model=model, api_key=api_key, groq_api_key=groq_api_key
            )

        if provider in ("cerebras", "cerebras_sdk", "cerebras_cloud"):
            return self._cerebras_generate(
                prompt, model=model, api_key=api_key, cerebras_api_key=cerebras_api_key
            )

        if provider in ("gemini_sdk", "gemini", "google_genai"):
            return self._gemini_generate(prompt, model=model, api_key=api_key)

        if provider in ("openai_compatible", "openai"):
            return self._openai_compatible_generate(
                prompt, model=model, api_key=api_key, api_base=api_base
            )

        LOGGER.error("Unsupported LLM_PROVIDER: %s", provider)
        self._last_error_kind = "config_error"
        return None

    def _cerebras_generate(
        self, prompt: str, *, model: str, api_key: str, cerebras_api_key: str
    ) -> Optional[str]:
        try:
            from cerebras.cloud.sdk import Cerebras
        except Exception:
            try:
                from cerebras_cloud_sdk import Cerebras
            except Exception as exc:  # pragma: no cover - optional dependency
                LOGGER.error("cerebras-cloud-sdk is not installed: %s", exc)
                self._last_error_kind = "dependency_error"
                return None

        resolved_key = cerebras_api_key or api_key
        if not resolved_key:
            LOGGER.error("CEREBRAS_API_KEY is not set")
            self._last_error_kind = "config_error"
            return None

        try:
            client = Cerebras(api_key=resolved_key)
            payload: dict[str, Any] = {
                "model": model,
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
            self._last_error_kind = _classify_error(exc)
            return None

        try:
            return response.choices[0].message.content
        except Exception:
            LOGGER.error("LLM response missing content")
            self._last_error_kind = "response_error"
            return None

    def _gemini_generate(
        self, prompt: str, *, model: str, api_key: str
    ) -> Optional[str]:
        try:
            from google import genai
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.error("google-genai is not installed: %s", exc)
            self._last_error_kind = "dependency_error"
            return None

        if not api_key:
            LOGGER.error("LLM_API_KEY is not set")
            self._last_error_kind = "config_error"
            return None

        try:
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={"temperature": self._temperature},
            )
        except Exception as exc:
            LOGGER.error("LLM request failed: %s", exc)
            self._last_error_kind = _classify_error(exc)
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
            self._last_error_kind = "response_error"
            return None

    def _openai_compatible_generate(
        self, prompt: str, *, model: str, api_key: str, api_base: str
    ) -> Optional[str]:
        if not api_base:
            LOGGER.error("LLM_API_BASE is not set")
            self._last_error_kind = "config_error"
            return None
        if not api_key:
            LOGGER.error("LLM_API_KEY is not set")
            self._last_error_kind = "config_error"
            return None

        payload: dict[str, Any] = {
            "model": model,
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
            "Authorization": f"Bearer {api_key}",
        }
        request = urllib.request.Request(
            api_base, data=body, headers=headers, method="POST"
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout_sec) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            LOGGER.error("LLM HTTP error: %s", exc)
            self._last_error_kind = _classify_error(exc)
            return None
        except urllib.error.URLError as exc:
            LOGGER.error("LLM connection error: %s", exc)
            self._last_error_kind = "connection_error"
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.error("LLM response not JSON")
            self._last_error_kind = "response_error"
            return None

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            LOGGER.error("LLM response missing content")
            self._last_error_kind = "response_error"
            return None

    def _groq_generate(
        self, prompt: str, *, model: str, api_key: str, groq_api_key: str
    ) -> Optional[str]:
        try:
            from groq import Groq
        except Exception as exc:  # pragma: no cover - optional dependency
            LOGGER.error("groq is not installed: %s", exc)
            self._last_error_kind = "dependency_error"
            return None

        resolved_key = groq_api_key or api_key
        if not resolved_key:
            LOGGER.error("GROQ_API_KEY is not set")
            self._last_error_kind = "config_error"
            return None

        try:
            client = Groq(api_key=resolved_key)
            payload: dict[str, Any] = {
                "model": model,
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
            self._last_error_kind = _classify_error(exc)
            return None

        try:
            return response.choices[0].message.content
        except Exception:
            LOGGER.error("LLM response missing content")
            self._last_error_kind = "response_error"
            return None

    def _ollama_generate(
        self, prompt: str, *, model: str, api_base: str
    ) -> Optional[str]:
        base = api_base.strip() if api_base else _OLLAMA_DEFAULT_BASE
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
            "model": model,
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
            self._last_error_kind = _classify_error(exc)
            return None
        except urllib.error.URLError as exc:
            LOGGER.error("LLM connection error: %s", exc)
            self._last_error_kind = "connection_error"
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            LOGGER.error("LLM response not JSON")
            self._last_error_kind = "response_error"
            return None

        message = data.get("message", {})
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        response_text = data.get("response")
        if isinstance(response_text, str) and response_text.strip():
            return response_text.strip()

        LOGGER.error("LLM response missing content")
        self._last_error_kind = "response_error"
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


def _needs_answer_key_fix(exc: ValidationError) -> bool:
    for err in exc.errors():
        loc = err.get("loc", ())
        if not loc:
            continue
        if loc[-1] == "answer_key":
            return True
    return False


def _parse_fallbacks(value: str) -> List[Dict[str, str]]:
    raw = (value or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        LOGGER.warning("Invalid fallback JSON: %s", exc)
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    cleaned: List[Dict[str, str]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        cleaned.append(
            {
                key: str(value).strip()
                for key, value in entry.items()
                if isinstance(value, (str, int, float)) and str(value).strip()
            }
        )
    return cleaned


def _mask_key(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if not raw:
        return "none"
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"


def _select_log_key(
    provider: Optional[str],
    api_key: Optional[str],
    groq_api_key: Optional[str],
    cerebras_api_key: Optional[str],
) -> Optional[str]:
    normalized = (provider or "").strip().lower()
    if normalized in ("groq", "groq_sdk", "groq_cloud"):
        return groq_api_key or api_key
    if normalized in ("cerebras", "cerebras_sdk", "cerebras_cloud"):
        return cerebras_api_key or api_key
    return api_key


def _classify_error(exc: Exception) -> str:
    if _is_rate_limit_error(exc):
        return "rate_limit"
    return "request_error"


def _is_rate_limit_error(exc: Exception) -> bool:
    for attr in ("status_code", "status", "code"):
        code = getattr(exc, attr, None)
        if code == 429:
            return True
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if code == 429:
            return True
    message = str(exc).lower()
    return (
        "rate limit" in message
        or "too many requests" in message
        or "429" in message
        or "quota" in message
        or "token quota" in message
        or "tokens per day" in message
        or "token_quota_exceeded" in message
        or "too many tokens" in message
    )


def _build_ollama_url(api_base: str) -> str:
    base = api_base.strip().rstrip("/")
    if base.endswith("/api/chat") or base.endswith("/api/generate"):
        return base
    return f"{base}/api/chat"
