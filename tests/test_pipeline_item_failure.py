from __future__ import annotations

from app.core.config import settings
from app.schemas.request import GenerateRequestItem
from app.schemas.response import Meta, Options, QuestionItem
from app.services import pipeline


def _ok_question(stem: str) -> tuple[QuestionItem, list]:
    question = QuestionItem(
        topic="t",
        competency="c",
        stem=stem,
        options=Options(A="a", B="b", C="c", D="d"),
        answer_key="A",
        explanation="e",
        evidence=[],
        status="OK",
        meta=Meta(retrieval={}, verification={}, timings_ms={}),
    )
    return question, []


def test_generic_exception_emits_error_and_preserves_completed_count(monkeypatch):
    """Regression for the _emit_item_failure extraction: the two duplicated
    except-blocks in run_pipeline_stream were merged into one generator
    helper called via `completed = yield from _emit_item_failure(...)`.
    This proves the yield-from return-value plumbing actually carries the
    updated `completed` counter back into the enclosing loop -- if it
    didn't, item 2's progress events below would restart from 0 instead
    of continuing from item 1's count."""
    monkeypatch.setattr(settings, "OK_ONLY_MODE", False)

    calls = {"n": 0}

    def _fake_get_retriever(kb_id: str):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return object()

    def _fake_generate_single_question(*_args, **_kwargs):
        return _ok_question("second item question")

    monkeypatch.setattr(pipeline, "_get_retriever", _fake_get_retriever)
    monkeypatch.setattr(pipeline, "_generate_single_question", _fake_generate_single_question)

    payload = [
        GenerateRequestItem(kb_id="kb-aaaaaaaaaaaa", keyword="topic a", n_questions=1),
        GenerateRequestItem(kb_id="kb-bbbbbbbbbbbb", keyword="topic b", n_questions=1),
    ]

    # matches how the WS route actually drives the stream (routes.py passes
    # include_failed=False), so a failed item's question surfaces as
    # "question_failed" rather than a "question" event carrying a
    # FAILED_VERIFICATION status.
    events = list(pipeline.run_pipeline_stream(payload, include_failed=False))

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["item_index"] == 1
    assert error_events[0]["message"] == "generation_failed"

    failed_events = [e for e in events if e.get("type") == "question_failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["item_index"] == 1

    question_events = [e for e in events if e.get("type") == "question"]
    assert len(question_events) == 1
    assert question_events[0]["item_index"] == 2

    progress_events = [
        e for e in events if e.get("type") == "progress" and e.get("stage") != "start"
    ]
    # item 1's failure counts as completed=1, item 2's success continues to completed=2
    assert [e["completed"] for e in progress_events] == [1, 2]


def test_value_error_uses_generic_message_and_warning_log(monkeypatch, caplog):
    """The ValueError branch is only reachable if an item bypasses Pydantic
    validation (n_questions>=1 is normally enforced at the schema level) --
    construct one directly to exercise it."""
    monkeypatch.setattr(settings, "OK_ONLY_MODE", True)
    monkeypatch.setattr(pipeline, "_get_retriever", lambda kb_id: object())

    bad_item = GenerateRequestItem.model_construct(
        kb_id="kb-aaaaaaaaaaaa", topic="t", competency="", n_questions=0, language="both"
    )

    with caplog.at_level("WARNING", logger="app.services.pipeline"):
        events = list(pipeline.run_pipeline_stream([bad_item], include_failed=True))

    # ValueError branch logs at warning level (not the full-traceback
    # `.exception()` used for generic exceptions) with the real message,
    # even though the client-facing event stays generic.
    assert "pipeline validation error" in caplog.text
    assert "n_questions must be >= 1" in caplog.text

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["message"] == "generation_failed"
    # OK_ONLY_MODE=True means no question/question_failed events, and no
    # per-question progress events (only the initial "start" progress event,
    # which fires unconditionally at the top of run_pipeline_stream).
    assert not [e for e in events if e.get("type") in ("question", "question_failed")]
    per_question_progress = [
        e for e in events if e.get("type") == "progress" and e.get("stage") != "start"
    ]
    assert per_question_progress == []
