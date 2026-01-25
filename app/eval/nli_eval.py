from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from app.schemas.response import QuestionItem

_MODEL = None
_TOKENIZER = None
_DEVICE = None


def _load_nli_model(model_name: str):
    global _MODEL, _TOKENIZER, _DEVICE
    if _MODEL is not None and _TOKENIZER is not None:
        return _MODEL, _TOKENIZER, _DEVICE

    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Missing dependencies for NLI eval. Install `torch` and `transformers`."
        ) from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.to(device)
    model.eval()

    _MODEL = model
    _TOKENIZER = tokenizer
    _DEVICE = device
    return model, tokenizer, device


def _infer_nli(
    premise: str,
    hypothesis: str,
    *,
    model_name: str,
    max_length: int = 512,
) -> Dict[str, float]:
    if not premise.strip() or not hypothesis.strip():
        return {"entailment": 0.0, "neutral": 0.0, "contradiction": 0.0}

    model, tokenizer, device = _load_nli_model(model_name)
    import torch
    import torch.nn.functional as F

    inputs = tokenizer(
        premise,
        hypothesis,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        logits = model(**inputs).logits[0]
        probs = F.softmax(logits, dim=-1)

    id2label = model.config.id2label or {}
    label_map: Dict[str, float] = {"entailment": 0.0, "neutral": 0.0, "contradiction": 0.0}
    for idx, prob in enumerate(probs.tolist()):
        label = str(id2label.get(idx, "")).lower()
        if "entail" in label:
            label_map["entailment"] = prob
        elif "contradict" in label:
            label_map["contradiction"] = prob
        elif "neutral" in label:
            label_map["neutral"] = prob

    # Fallback if labels are unknown: use max prob as entailment proxy.
    if not any(label_map.values()):
        label_map["entailment"] = max(probs.tolist())
    return label_map


@dataclass
class NLIEvalResult:
    total_seen: int
    scored: int
    skipped_status: int
    skipped_no_evidence: int
    avg_entailment: float
    label_counts: Dict[str, int]
    items: Optional[List[Dict[str, object]]]


def evaluate_question_bank_nli(
    path: str,
    *,
    model_name: str,
    limit: int = 0,
    include_items: bool = False,
    max_length: int = 512,
) -> NLIEvalResult:
    bank_path = Path(path)
    total_seen = 0
    scored = 0
    skipped_status = 0
    skipped_no_evidence = 0
    entailment_sum = 0.0
    label_counts = {"entailment": 0, "neutral": 0, "contradiction": 0}
    items: List[Dict[str, object]] = []

    if not bank_path.exists():
        return NLIEvalResult(
            total_seen=0,
            scored=0,
            skipped_status=0,
            skipped_no_evidence=0,
            avg_entailment=0.0,
            label_counts=label_counts,
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
            hypothesis = f"{question.stem} {answer_text}".strip()
            scores = _infer_nli(
                evidence_text,
                hypothesis,
                model_name=model_name,
                max_length=max_length,
            )
            entailment = scores.get("entailment", 0.0)
            label = max(scores.items(), key=lambda item: item[1])[0]

            scored += 1
            entailment_sum += entailment
            label_counts[label] = label_counts.get(label, 0) + 1

            if include_items:
                items.append(
                    {
                        "topic": question.topic,
                        "competency": question.competency,
                        "stem": question.stem,
                        "answer_key": question.answer_key,
                        "answer_text": answer_text,
                        "entailment": entailment,
                        "neutral": scores.get("neutral", 0.0),
                        "contradiction": scores.get("contradiction", 0.0),
                        "label": label,
                        "evidence_doc_ids": [ev.doc_id for ev in question.evidence],
                    }
                )

    avg_entailment = entailment_sum / scored if scored else 0.0
    return NLIEvalResult(
        total_seen=total_seen,
        scored=scored,
        skipped_status=skipped_status,
        skipped_no_evidence=skipped_no_evidence,
        avg_entailment=avg_entailment,
        label_counts=label_counts,
        items=items if include_items else None,
    )
