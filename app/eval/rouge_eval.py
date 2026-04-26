from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from app.schemas.response import QuestionItem

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _rouge_1_f1(candidate: str, reference: str) -> float:
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0

    ref_counts: Dict[str, int] = {}
    for token in ref_tokens:
        ref_counts[token] = ref_counts.get(token, 0) + 1

    overlap = 0
    for token in cand_tokens:
        count = ref_counts.get(token, 0)
        if count > 0:
            overlap += 1
            ref_counts[token] = count - 1

    precision = overlap / len(cand_tokens)
    recall = overlap / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _lcs_length(a_tokens: List[str], b_tokens: List[str]) -> int:
    if not a_tokens or not b_tokens:
        return 0

    prev = [0] * (len(b_tokens) + 1)
    for token in a_tokens:
        curr = [0]
        for j, b_token in enumerate(b_tokens, start=1):
            if token == b_token:
                curr.append(prev[j - 1] + 1)
            else:
                curr.append(max(curr[-1], prev[j]))
        prev = curr
    return prev[-1]


def _rouge_l_f1(candidate: str, reference: str) -> float:
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0

    lcs = _lcs_length(cand_tokens, ref_tokens)
    precision = lcs / len(cand_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _category(rouge_l: float) -> str:
    if rouge_l >= 0.30:
        return "strong"
    if rouge_l >= 0.20:
        return "moderate"
    if rouge_l >= 0.10:
        return "weak"
    return "very_weak"


@dataclass
class RougeEvalResult:
    total_seen: int
    scored: int
    skipped_status: int
    skipped_no_evidence: int
    avg_rouge1_f1: float
    avg_rougeL_f1: float
    categories: Dict[str, int]
    items: Optional[List[Dict[str, object]]]


def evaluate_question_bank(
    path: str,
    *,
    limit: int = 0,
    include_items: bool = False,
    filter_category: Optional[str] = None,
) -> RougeEvalResult:
    bank_path = Path(path)
    total_seen = 0
    scored = 0
    skipped_status = 0
    skipped_no_evidence = 0
    rouge1_sum = 0.0
    rougel_sum = 0.0
    categories = {"strong": 0, "moderate": 0, "weak": 0, "very_weak": 0}
    items: List[Dict[str, object]] = []

    if not bank_path.exists():
        return RougeEvalResult(
            total_seen=0,
            scored=0,
            skipped_status=0,
            skipped_no_evidence=0,
            avg_rouge1_f1=0.0,
            avg_rougeL_f1=0.0,
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
            rouge1_f1 = _rouge_1_f1(combined_text, evidence_text)
            rougel_f1 = _rouge_l_f1(combined_text, evidence_text)
            category = _category(rougel_f1)
            if filter_category and category != filter_category:
                continue

            scored += 1
            rouge1_sum += rouge1_f1
            rougel_sum += rougel_f1
            categories[category] += 1

            if include_items:
                items.append(
                    {
                        "topic": question.topic,
                        "competency": question.competency,
                        "stem": question.stem,
                        "answer_text": answer_text,
                        "rouge1_f1": rouge1_f1,
                        "rougeL_f1": rougel_f1,
                        "category": category,
                        "evidence_doc_ids": [ev.doc_id for ev in question.evidence],
                    }
                )

    avg_rouge1_f1 = rouge1_sum / scored if scored else 0.0
    avg_rougeL_f1 = rougel_sum / scored if scored else 0.0

    return RougeEvalResult(
        total_seen=total_seen,
        scored=scored,
        skipped_status=skipped_status,
        skipped_no_evidence=skipped_no_evidence,
        avg_rouge1_f1=avg_rouge1_f1,
        avg_rougeL_f1=avg_rougeL_f1,
        categories=categories,
        items=items if include_items else None,
    )
