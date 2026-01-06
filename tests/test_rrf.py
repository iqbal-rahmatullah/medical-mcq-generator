from __future__ import annotations

from app.retrieval.retriever import rrf_fuse


def test_rrf_promotes_consistent_rank() -> None:
    rank_a = ["d1", "d2", "d3", "d4"]
    rank_b = ["d2", "d3", "d4", "d1"]

    fused = rrf_fuse(rank_a, rank_b, k_rrf=1)

    assert fused.index("d2") < fused.index("d1")
