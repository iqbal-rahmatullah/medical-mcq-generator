from __future__ import annotations

from app.core.config import settings
from app.schemas.request import GenerateRequestItem
from app.services import pipeline


def test_run_pipeline_stream_selects_retriever_per_item(monkeypatch):
    """Regression: run_pipeline_stream used to resolve the retriever once
    from payload[0].kb_id and reuse it for every item in the batch, even
    though kb_id is a per-item field. A batch mixing two knowledge bases
    would silently generate every item after the first against the wrong
    KB. Assert _get_retriever is called once per item with that item's
    own kb_id, in payload order."""
    monkeypatch.setattr(settings, "OK_ONLY_MODE", True)
    monkeypatch.setattr(settings, "QUESTION_BANK_FALLBACK", False)

    calls: list[str] = []

    def _fake_get_retriever(kb_id: str):
        calls.append(kb_id)
        return None  # forces the cheap "retriever unavailable" error path

    monkeypatch.setattr(pipeline, "_get_retriever", _fake_get_retriever)

    payload = [
        GenerateRequestItem(kb_id="kb-aaaaaaaaaaaa", keyword="topic a", n_questions=1),
        GenerateRequestItem(kb_id="kb-bbbbbbbbbbbb", keyword="topic b", n_questions=1),
        GenerateRequestItem(kb_id="kb-aaaaaaaaaaaa", keyword="topic c", n_questions=1),
    ]

    events = list(pipeline.run_pipeline_stream(payload, include_failed=True))

    assert calls == ["kb-aaaaaaaaaaaa", "kb-bbbbbbbbbbbb", "kb-aaaaaaaaaaaa"]

    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 3
    assert [e["item_index"] for e in error_events] == [1, 2, 3]
