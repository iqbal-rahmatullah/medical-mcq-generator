from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from app.schemas.response import QuestionItem

_MODEL = None
_TOKENIZER = None
_DEVICE = None


def _load_embedding_model(model_name: str):
    global _MODEL, _TOKENIZER, _DEVICE
    if _MODEL is not None and _TOKENIZER is not None:
        return _MODEL, _TOKENIZER, _DEVICE

    try:
        import torch
        from transformers import AutoModel, AutoTokenizer
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Missing dependencies for semantic eval. Install `torch` and `transformers`."
        ) from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.to(device)
    model.eval()

    _MODEL = model
    _TOKENIZER = tokenizer
    _DEVICE = device
    return model, tokenizer, device


def _mean_pool(last_hidden, attention_mask):
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden.size()).float()
    summed = torch.sum(last_hidden * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def _embed(text: str, *, model_name: str, max_length: int = 512):
    if not text.strip():
        return None

    model, tokenizer, device = _load_embedding_model(model_name)
    import torch

    inputs = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        outputs = model(**inputs)
    pooled = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"])
    return pooled[0]


def _cosine_similarity(vec_a, vec_b) -> float:
    import torch

    if vec_a is None or vec_b is None:
        return 0.0
    a = vec_a / (torch.norm(vec_a) + 1e-9)
    b = vec_b / (torch.norm(vec_b) + 1e-9)
    return float(torch.dot(a, b).item())


def _category(score: float) -> str:
    if score >= 0.70:
        return "strong"
    if score >= 0.50:
        return "moderate"
    if score >= 0.30:
        return "weak"
    return "very_weak"


@dataclass
class SemanticEvalResult:
    total_seen: int
    scored: int
    skipped_status: int
    skipped_no_evidence: int
    avg_cosine: float
    categories: Dict[str, int]
    items: Optional[List[Dict[str, object]]]


def evaluate_question_bank_semantic(
    path: str,
    *,
    model_name: str,
    limit: int = 0,
    include_items: bool = False,
    max_length: int = 512,
    filter_category: Optional[str] = None,
) -> SemanticEvalResult:
    bank_path = Path(path)
    total_seen = 0
    scored = 0
    skipped_status = 0
    skipped_no_evidence = 0
    cosine_sum = 0.0
    categories = {"strong": 0, "moderate": 0, "weak": 0, "very_weak": 0}
    items: List[Dict[str, object]] = []

    if not bank_path.exists():
        return SemanticEvalResult(
            total_seen=0,
            scored=0,
            skipped_status=0,
            skipped_no_evidence=0,
            avg_cosine=0.0,
            categories=categories,
            items=[] if include_items else None,
        )

    with bank_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if limit and total_seen >= limit:
                break
            line = line.strip()
            if not line:
                continue
            total_seen += 1
            try:
                payload = json.loads(line)
                question = QuestionItem.model_validate(payload)
            except Exception:
                continue

            if question.status != "OK":
                skipped_status += 1
                continue

            evidence_text = " ".join(
                evidence.span_text for evidence in question.evidence if evidence.span_text
            ).strip()
            if not evidence_text:
                skipped_no_evidence += 1
                continue

            answer_text = getattr(question.options, question.answer_key, "")
            combined_text = f"{question.stem} {answer_text}".strip()

            emb_a = _embed(combined_text, model_name=model_name, max_length=max_length)
            emb_b = _embed(evidence_text, model_name=model_name, max_length=max_length)
            cosine = _cosine_similarity(emb_a, emb_b)
            category = _category(cosine)
            if filter_category and category != filter_category:
                continue

            scored += 1
            cosine_sum += cosine
            categories[category] += 1

            if include_items:
                items.append(
                    {
                        "topic": question.topic,
                        "competency": question.competency,
                        "stem": question.stem,
                        "answer_key": question.answer_key,
                        "answer_text": answer_text,
                        "cosine_similarity": cosine,
                        "category": category,
                        "evidence_doc_ids": [ev.doc_id for ev in question.evidence],
                    }
                )

    avg_cosine = cosine_sum / scored if scored else 0.0
    return SemanticEvalResult(
        total_seen=total_seen,
        scored=scored,
        skipped_status=skipped_status,
        skipped_no_evidence=skipped_no_evidence,
        avg_cosine=avg_cosine,
        categories=categories,
        items=items if include_items else None,
    )
