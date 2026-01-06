from __future__ import annotations

from app.corpus.models import Document
from app.retrieval.bm25 import BM25Index
from app.retrieval.retriever import Retriever


def _make_docs() -> list[Document]:
    return [
        Document(
            doc_id="d1",
            source="test",
            title="Diabetes diagnosis",
            text="Symptoms include polyuria and polydipsia.",
        ),
        Document(
            doc_id="d2",
            source="test",
            title="Hypertension management",
            text="Lifestyle modification remains first-line therapy.",
        ),
        Document(
            doc_id="d3",
            source="test",
            title="Asthma exacerbation",
            text="Triggers include allergens and infections.",
        ),
        Document(
            doc_id="d4",
            source="test",
            title="Diabetes treatment",
            text="Metformin improves insulin sensitivity.",
        ),
        Document(
            doc_id="d5",
            source="test",
            title="Thyroid disorders",
            text="Hypothyroidism causes fatigue and weight gain.",
        ),
    ]


class _DummyRuntime:
    def __init__(self) -> None:
        self.called = False

    def rerank(self, query: str, docs: list[Document]) -> list[float]:
        self.called = True
        return [float(len(docs) - idx) for idx in range(len(docs))]


def test_bm25_only_does_not_call_medcpt() -> None:
    index = BM25Index.build(_make_docs())
    runtime = _DummyRuntime()

    retriever = Retriever(
        index,
        medcpt_runtime=runtime,
        retrieval_mode="bm25_only",
        bm25_candidates_top_n=5,
        rerank_top_n=3,
        evidence_top_k=2,
    )
    retriever.retrieve("diabetes", "diagnosis")

    assert runtime.called is False


def test_hybrid_mode_calls_medcpt() -> None:
    index = BM25Index.build(_make_docs())
    runtime = _DummyRuntime()

    retriever = Retriever(
        index,
        medcpt_runtime=runtime,
        retrieval_mode="hybrid_rerank",
        bm25_candidates_top_n=5,
        rerank_top_n=3,
        evidence_top_k=2,
    )
    retriever.retrieve("diabetes", "diagnosis")

    assert runtime.called is True
