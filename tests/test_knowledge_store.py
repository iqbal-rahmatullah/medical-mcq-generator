from __future__ import annotations

import pytest

from app.core.config import settings
from app.ingestion import knowledge_store as kb_store


@pytest.fixture(autouse=True)
def _isolated_kb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "KNOWLEDGE_DIR", str(tmp_path))
    yield


def test_is_valid_kb_id_accepts_generated_ids():
    manifest = kb_store.create_kb("Sample KB", ["a.txt"])
    assert kb_store.is_valid_kb_id(manifest["id"])


@pytest.mark.parametrize(
    "bad_id",
    ["../../etc", "..", "a/b", "a\\b", "", "UPPERCASE12", "short", "has spaces12"],
)
def test_is_valid_kb_id_rejects_malformed_ids(bad_id):
    assert kb_store.is_valid_kb_id(bad_id) is False


def test_kb_dir_raises_on_path_traversal_id():
    with pytest.raises(ValueError):
        kb_store._kb_dir("../../etc")


def test_kb_dir_does_not_escape_knowledge_root(tmp_path):
    with pytest.raises(ValueError):
        kb_store.raw_dir("../outside")
    # nothing was created outside the isolated KNOWLEDGE_DIR
    assert not (tmp_path.parent / "outside").exists()


def test_get_kb_returns_none_for_traversal_id():
    # regression: previously this would read manifest.json from an
    # attacker-controlled path instead of safely reporting not-found
    assert kb_store.get_kb("../../etc/passwd") is None


def test_delete_kb_refuses_traversal_id(tmp_path):
    outside = tmp_path.parent / "sentinel"
    outside.mkdir(exist_ok=True)
    marker = outside / "keep.txt"
    marker.write_text("do not delete me")

    with pytest.raises(ValueError):
        kb_store.delete_kb("../sentinel")

    # the traversal attempt must not have reached shutil.rmtree
    assert marker.exists()


def test_remove_file_sanitizes_filename_traversal(tmp_path):
    manifest = kb_store.create_kb("Sample KB", ["a.txt"])
    kb_id = manifest["id"]
    raw = kb_store.raw_dir(kb_id)
    (raw / "a.txt").write_text("hello")

    outside = tmp_path.parent / "victim.txt"
    outside.write_text("do not delete me")

    # a filename that looks like a traversal attempt must resolve to a
    # (nonexistent) name inside raw/, never escape to the sibling file
    kb_store.remove_file(kb_id, "../../victim.txt")

    assert outside.exists()
    assert (raw / "a.txt").exists()


@pytest.mark.parametrize("dotname", [".", ".."])
def test_remove_file_rejects_bare_dot_segments(dotname):
    """Regression: Path(x).name does not collapse a bare '.'/'..' filename
    (unlike multi-segment traversal, which does get reduced to its last
    component). Without an explicit reject, remove_file() would try to
    unlink the KB's own raw/ directory and raise an unhandled
    IsADirectoryError/PermissionError instead of a clean no-op."""
    manifest = kb_store.create_kb("Sample KB", ["a.txt"])
    kb_id = manifest["id"]
    raw = kb_store.raw_dir(kb_id)
    (raw / "a.txt").write_text("hello")

    # must not raise, and must not touch the raw/ directory itself
    kb_store.remove_file(kb_id, dotname)
    assert raw.is_dir()
    assert (raw / "a.txt").exists()


def test_remove_file_removes_the_intended_file():
    manifest = kb_store.create_kb("Sample KB", ["a.txt", "b.txt"])
    kb_id = manifest["id"]
    raw = kb_store.raw_dir(kb_id)
    (raw / "a.txt").write_text("hello")
    (raw / "b.txt").write_text("world")

    updated = kb_store.remove_file(kb_id, "a.txt")

    assert not (raw / "a.txt").exists()
    assert (raw / "b.txt").exists()
    assert "a.txt" not in updated["files"]
