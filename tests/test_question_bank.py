from __future__ import annotations

from app.logging import question_bank as qb
from app.schemas.response import Meta, Options, QuestionItem


def _make_question(stem: str) -> QuestionItem:
    return QuestionItem(
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


def test_load_question_bank_missing_file_returns_empty(tmp_path):
    path = str(tmp_path / "missing.jsonl")
    assert qb.load_question_bank(path) == []


def test_append_then_load_round_trips(tmp_path):
    path = str(tmp_path / "bank.jsonl")
    qb.append_question_bank(path, _make_question("s1"))
    loaded = qb.load_question_bank(path)
    assert len(loaded) == 1
    assert loaded[0].stem == "s1"


def test_append_skips_non_ok_questions(tmp_path):
    path = str(tmp_path / "bank.jsonl")
    q = _make_question("bad")
    q.status = "FAILED_VERIFICATION"
    qb.append_question_bank(path, q)
    assert qb.load_question_bank(path) == []


def test_repeated_load_uses_cache_and_still_reflects_appends(tmp_path):
    """Regression: load_question_bank() used to re-parse the whole JSONL
    file on every call. Two loads with no intervening append should be
    served from cache; an append in between must still be visible on the
    next load without requiring a fresh full-file parse to pick it up."""
    path = str(tmp_path / "bank.jsonl")

    assert qb.load_question_bank(path) == []
    qb.append_question_bank(path, _make_question("s1"))

    first = qb.load_question_bank(path)
    second = qb.load_question_bank(path)
    assert len(first) == 1
    assert len(second) == 1
    # cache returns independent copies, not a shared mutable list
    first.append(_make_question("mutated"))
    assert len(qb.load_question_bank(path)) == 1

    qb.append_question_bank(path, _make_question("s2"))
    third = qb.load_question_bank(path)
    assert len(third) == 2
    assert {q.stem for q in third} == {"s1", "s2"}


def test_cache_is_keyed_per_path_not_global(tmp_path):
    path_a = str(tmp_path / "a.jsonl")
    path_b = str(tmp_path / "b.jsonl")
    qb.append_question_bank(path_a, _make_question("only-in-a"))
    assert qb.load_question_bank(path_b) == []
    assert len(qb.load_question_bank(path_a)) == 1
