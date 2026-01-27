from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from app.corpus.models import Document

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())

@dataclass(frozen=True)
class BM25Config:
    k1: float = 1.5
    b: float = 0.75


class BM25Index:
    def __init__(
        self,
        docs: List[Document],
        doc_term_freqs: List[Dict[str, int]],
        doc_lens: List[int],
        idf: Dict[str, float],
        avgdl: float,
        config: BM25Config | None = None,
    ) -> None:
        self._docs = docs
        self._doc_term_freqs = doc_term_freqs
        self._doc_lens = doc_lens
        self._idf = idf
        self._avgdl = avgdl
        self._config = config or BM25Config()

    @classmethod
    def build(cls, doc_stream: Iterable[Document], config: BM25Config | None = None) -> "BM25Index":
        docs: List[Document] = []
        doc_term_freqs: List[Dict[str, int]] = []
        doc_lens: List[int] = []
        doc_freqs: Dict[str, int] = {}

        for doc in doc_stream:
            tokens = _tokenize(f"{doc.title} {doc.text}")
            term_freqs: Dict[str, int] = {}
            for token in tokens:
                term_freqs[token] = term_freqs.get(token, 0) + 1
            docs.append(doc)
            doc_term_freqs.append(term_freqs)
            doc_lens.append(len(tokens))

            for term in term_freqs.keys():
                doc_freqs[term] = doc_freqs.get(term, 0) + 1

        total_docs = len(docs)
        avgdl = sum(doc_lens) / total_docs if total_docs else 0.0
        idf: Dict[str, float] = {}
        for term, df in doc_freqs.items():
            idf[term] = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))

        return cls(docs, doc_term_freqs, doc_lens, idf, avgdl, config)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Document, float]]:
        if not self._docs or not query.strip() or self._avgdl == 0.0:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        k1 = self._config.k1
        b = self._config.b
        scores: List[Tuple[Document, float]] = []

        for doc, term_freqs, doc_len in zip(
            self._docs, self._doc_term_freqs, self._doc_lens
        ):
            score = 0.0
            for term in tokens:
                tf = term_freqs.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = tf + k1 * (1 - b + b * (doc_len / self._avgdl))
                score += idf * (tf * (k1 + 1)) / denom
            if score > 0.0:
                scores.append((doc, score))

        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[: max(top_k, 0)]
