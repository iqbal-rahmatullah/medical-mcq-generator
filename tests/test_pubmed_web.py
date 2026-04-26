from __future__ import annotations

from unittest.mock import patch

from app.corpus.models import Document
from app.retrieval import pubmed_web
from app.retrieval.pubmed_web import fetch_pubmed_documents


def test_esearch_parses_id_list() -> None:
    payload = {"esearchresult": {"idlist": ["123", "456"]}}
    with patch("app.retrieval.pubmed_web._fetch_json", return_value=payload):
        ids = pubmed_web._esearch(
            "asthma prevention",
            max_results=2,
            api_key=None,
            email=None,
            timeout_sec=5.0,
        )

    assert ids == ["123", "456"]


def test_efetch_parses_articles() -> None:
    xml = (
        "<PubmedArticleSet>"
        "<PubmedArticle>"
        "<MedlineCitation>"
        "<PMID>123</PMID>"
        "<Article>"
        "<ArticleTitle>Sample Title</ArticleTitle>"
        "<Abstract>"
        "<AbstractText Label=\"BACKGROUND\">Background text.</AbstractText>"
        "<AbstractText>More text.</AbstractText>"
        "</Abstract>"
        "</Article>"
        "</MedlineCitation>"
        "</PubmedArticle>"
        "</PubmedArticleSet>"
    )
    with patch("app.retrieval.pubmed_web._fetch_text", return_value=xml):
        docs = pubmed_web._efetch(
            ["123"],
            api_key=None,
            email=None,
            timeout_sec=5.0,
        )

    assert len(docs) == 1
    assert docs[0].doc_id == "pubmed_web_123"
    assert docs[0].source == "pubmed_web"
    assert docs[0].title == "Sample Title"
    assert "BACKGROUND:" in docs[0].text


def test_fetch_pubmed_documents_returns_docs() -> None:
    expected = [
        Document(
            doc_id="pubmed_web_789",
            source="pubmed_web",
            title="Test Title",
            text="Test abstract",
        )
    ]
    with patch("app.retrieval.pubmed_web._esearch", return_value=["789"]):
        with patch("app.retrieval.pubmed_web._efetch", return_value=expected):
            docs = fetch_pubmed_documents(
                "stroke prevention",
                max_results=1,
                api_key=None,
                email=None,
                timeout_sec=5.0,
            )

    assert docs == expected


def test_fetch_pubmed_documents_handles_esearch_error() -> None:
    with patch("app.retrieval.pubmed_web._esearch", side_effect=RuntimeError("boom")):
        docs = fetch_pubmed_documents(
            "stroke prevention",
            max_results=1,
            api_key=None,
            email=None,
            timeout_sec=5.0,
        )

    assert docs == []
