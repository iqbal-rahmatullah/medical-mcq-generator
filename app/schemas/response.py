from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, TypeAdapter


class HealthResponse(BaseModel):
    status: str


class EvidenceItem(BaseModel):
    source: str
    doc_id: str
    title: str
    span_text: str


class Options(BaseModel):
    A: str
    B: str
    C: str
    D: str


class Meta(BaseModel):
    retrieval: Dict[str, Any] = Field(default_factory=dict)
    verification: Dict[str, Any] = Field(default_factory=dict)
    timings_ms: Dict[str, float] = Field(default_factory=dict)


QuestionStatus = Literal["OK", "INSUFFICIENT_EVIDENCE", "FAILED_VERIFICATION"]
AnswerKey = Literal["A", "B", "C", "D"]


class QuestionItem(BaseModel):
    topic: str
    competency: str
    stem: str
    options: Options
    answer_key: AnswerKey
    explanation: str
    evidence: List[EvidenceItem]
    status: QuestionStatus
    meta: Meta = Field(default_factory=Meta)
    stem_id: str = ""
    options_id: Optional[Options] = None
    explanation_id: str = ""


def export_question_schema() -> Dict[str, Any]:
    return QuestionItem.model_json_schema()


def export_generate_response_schema() -> Dict[str, Any]:
    adapter = TypeAdapter(List[QuestionItem])
    return adapter.json_schema()
