from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Iterable, List, Optional

from app.corpus.models import Document

LOGGER = logging.getLogger(__name__)

_WHITESPACE_RE = None


def _normalize_text(value: str) -> str:
    global _WHITESPACE_RE
    if _WHITESPACE_RE is None:
        import re

        _WHITESPACE_RE = re.compile(r"\s+")
    return _WHITESPACE_RE.sub(" ", value.strip())


def _build_query_params(params: dict[str, str]) -> str:
    return urllib.parse.urlencode(params, doseq=True)


def _fetch_json(url: str, timeout_sec: float) -> dict:
    with urllib.request.urlopen(url, timeout=timeout_sec) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def _fetch_text(url: str, timeout_sec: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout_sec) as response:
        return response.read().decode("utf-8")


def _esearch(
    term: str,
    max_results: int,
    api_key: Optional[str],
    email: Optional[str],
    timeout_sec: float,
) -> List[str]:
    if not term or max_results <= 0:
        return []
    params = {
        "db": "pubmed",
        "retmode": "json",
        "retmax": str(max_results),
        "term": term,
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + _build_query_params(
        params
    )
    data = _fetch_json(url, timeout_sec)
    return list(data.get("esearchresult", {}).get("idlist", []) or [])


def _efetch(
    pmids: Iterable[str],
    api_key: Optional[str],
    email: Optional[str],
    timeout_sec: float,
) -> List[Document]:
    pmid_list = [pmid for pmid in pmids if pmid]
    if not pmid_list:
        return []
    params = {
        "db": "pubmed",
        "retmode": "xml",
        "id": ",".join(pmid_list),
    }
    if api_key:
        params["api_key"] = api_key
    if email:
        params["email"] = email
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + _build_query_params(
        params
    )
    xml_text = _fetch_text(url, timeout_sec)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        LOGGER.warning("PubMed efetch parse error: %s", exc)
        return []

    documents: List[Document] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID")
        title = article.findtext(".//ArticleTitle") or ""
        abstract_parts = []
        for node in article.findall(".//AbstractText"):
            if node.text:
                label = node.attrib.get("Label")
                if label:
                    abstract_parts.append(f"{label}: {node.text}")
                else:
                    abstract_parts.append(node.text)
        abstract = " ".join(abstract_parts).strip()
        title = _normalize_text(title)
        abstract = _normalize_text(abstract)
        text = abstract or title
        if not pmid or not text:
            continue
        documents.append(
            Document(
                doc_id=f"pubmed_web_{pmid}",
                source="pubmed_web",
                title=title,
                text=text,
            )
        )
    return documents


def fetch_pubmed_documents(
    term: str,
    max_results: int,
    *,
    api_key: Optional[str] = None,
    email: Optional[str] = None,
    timeout_sec: float = 10.0,
) -> List[Document]:
    try:
        pmids = _esearch(
            term,
            max_results=max_results,
            api_key=api_key,
            email=email,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        LOGGER.warning("PubMed esearch failed: %s", exc)
        return []

    try:
        return _efetch(
            pmids,
            api_key=api_key,
            email=email,
            timeout_sec=timeout_sec,
        )
    except Exception as exc:
        LOGGER.warning("PubMed efetch failed: %s", exc)
        return []
