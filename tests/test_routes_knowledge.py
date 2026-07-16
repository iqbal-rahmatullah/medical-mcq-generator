from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _isolated_kb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_DIR", str(tmp_path))
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _generate_payload(kb_id: str) -> list[dict]:
    return [{"kb_id": kb_id, "keyword": "topic", "n_questions": 1, "language": "both"}]


def test_get_knowledge_malformed_kb_id_returns_404_not_found(client):
    # not a `/`-containing segment, so this actually reaches our route and
    # exercises Depends(_existing_kb) rather than being normalized away by
    # Starlette's own path resolution before dispatch.
    resp = client.get("/knowledge/not-a-valid-id")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not_found"


def test_get_knowledge_path_traversal_returns_404(client):
    # `..`-containing segments get resolved by Starlette's routing before
    # our dependency ever runs; still ends in 404, just via a different path.
    resp = client.get("/knowledge/..%2f..%2fetc")
    assert resp.status_code == 404


def test_delete_knowledge_malformed_kb_id_returns_404_not_found(client):
    resp = client.delete("/knowledge/not-a-valid-id")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "not_found"


def test_generate_rejects_malformed_kb_id_without_500(client):
    # kb_id here comes from the request body, not a path param, so it
    # bypasses the route-level Depends(_valid_kb_id) guard entirely --
    # this is the path that regressed to an unhandled ValueError/500
    # before knowledge_store.get_kb() was made traversal-safe.
    resp = client.post("/generate", json=_generate_payload("../../etc/passwd"))
    assert resp.status_code == 409
    assert "knowledge_not_found" in resp.json()["detail"]


def test_generate_rejects_nonexistent_well_formed_kb_id(client):
    resp = client.post("/generate", json=_generate_payload("abcdef123456"))
    assert resp.status_code == 409
    assert "knowledge_not_found" in resp.json()["detail"]


def test_ws_generate_rejects_malformed_kb_id_without_crash(client):
    with client.websocket_connect("/ws/generate") as ws:
        ws.send_json(_generate_payload("../../etc/passwd"))
        event = ws.receive_json()
        assert event["type"] == "error"
        assert "knowledge_not_found" in event["message"]


@pytest.mark.parametrize("dotname", [".", ".."])
def test_create_knowledge_rejects_bare_dot_segment_filename(client, dotname):
    """Regression: a bare '.'/'..' upload filename survives Path(x).name
    unchanged, so it used to reach dest.open("wb") pointed at the KB's own
    directory and raise an unhandled IsADirectoryError (500) instead of a
    clean 400."""
    resp = client.post(
        "/knowledge",
        data={"title": "Dot Segment KB"},
        files=[("files", (dotname, io.BytesIO(b"data"), "text/plain"))],
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_filename"
