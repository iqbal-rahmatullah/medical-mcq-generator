from __future__ import annotations

from app.core.config import settings
from app.logging import question_bank as qb
from app.schemas.request import GenerateRequestItem
from app.schemas.response import Meta, Options, QuestionItem
from app.services import pipeline


def _always_failing_question(*_args, **_kwargs):
    question = QuestionItem(
        topic="t",
        competency="c",
        stem="best effort stem",
        options=Options(A="a", B="b", C="c", D="d"),
        answer_key="A",
        explanation="e",
        evidence=[],
        status="FAILED_VERIFICATION",
        meta=Meta(retrieval={}, verification={}, timings_ms={}),
    )
    return question, []


def test_graceful_fallback_question_is_not_written_to_bank(tmp_path, monkeypatch):
    """Regression: a question that only reaches status=OK via the
    'graceful fallback' best-effort path (never actually passed
    verification) used to be written into the question bank like any
    other OK question when QUESTION_BANK_WRITE_OK was on, permanently
    polluting future fallback selection with ungrounded questions."""
    bank_path = tmp_path / "bank.jsonl"
    monkeypatch.setattr(settings, "OK_ONLY_MODE", True)
    monkeypatch.setattr(settings, "OK_ONLY_MAX_ROUNDS", 1)
    monkeypatch.setattr(settings, "QUESTION_BANK_FALLBACK", False)
    monkeypatch.setattr(settings, "QUESTION_BANK_WRITE_OK", True)
    monkeypatch.setattr(settings, "QUESTION_BANK_PATH", str(bank_path))

    monkeypatch.setattr(pipeline, "_get_retriever", lambda kb_id: object())
    monkeypatch.setattr(pipeline, "_generate_single_question", _always_failing_question)

    payload = [
        GenerateRequestItem(kb_id="kb-aaaaaaaaaaaa", keyword="topic", n_questions=1),
    ]

    events = list(pipeline.run_pipeline_stream(payload, include_failed=True))

    question_events = [e for e in events if e.get("type") == "question"]
    assert len(question_events) == 1
    emitted = question_events[0]["question"]
    assert emitted["status"] == "OK"
    assert emitted["meta"]["verification"].get("graceful_fallback") is True

    # the whole point of the fix: graceful-fallback questions must not
    # land in the bank even though QUESTION_BANK_WRITE_OK is on
    assert qb.load_question_bank(str(bank_path)) == []
    assert not bank_path.exists() or bank_path.read_text().strip() == ""


def test_genuinely_ok_question_is_still_written_to_bank(tmp_path, monkeypatch):
    """Sanity check the fix didn't over-broaden: a question that passes
    verification normally (status OK, no graceful_fallback flag) must
    still be persisted when QUESTION_BANK_WRITE_OK is on."""
    bank_path = tmp_path / "bank.jsonl"
    monkeypatch.setattr(settings, "OK_ONLY_MODE", True)
    monkeypatch.setattr(settings, "QUESTION_BANK_FALLBACK", False)
    monkeypatch.setattr(settings, "QUESTION_BANK_WRITE_OK", True)
    monkeypatch.setattr(settings, "QUESTION_BANK_PATH", str(bank_path))

    def _always_ok_question(*_args, **_kwargs):
        question = QuestionItem(
            topic="t",
            competency="c",
            stem="a genuinely verified stem",
            options=Options(A="a", B="b", C="c", D="d"),
            answer_key="A",
            explanation="e",
            evidence=[],
            status="OK",
            meta=Meta(retrieval={}, verification={}, timings_ms={}),
        )
        return question, []

    monkeypatch.setattr(pipeline, "_get_retriever", lambda kb_id: object())
    monkeypatch.setattr(pipeline, "_generate_single_question", _always_ok_question)

    payload = [
        GenerateRequestItem(kb_id="kb-aaaaaaaaaaaa", keyword="topic", n_questions=1),
    ]

    list(pipeline.run_pipeline_stream(payload, include_failed=True))

    bank = qb.load_question_bank(str(bank_path))
    assert len(bank) == 1
    assert bank[0].stem == "a genuinely verified stem"
