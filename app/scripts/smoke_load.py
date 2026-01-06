from __future__ import annotations

import argparse
from itertools import islice

from app.corpus.loaders import load_pubmed_jsonl, load_textbooks_jsonl
from app.corpus.store import DocumentStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test corpus loaders")
    parser.add_argument("--pubmed", type=str, required=True, help="Path to pubmed jsonl")
    parser.add_argument("--textbooks", type=str, required=True, help="Path to textbook jsonl")
    parser.add_argument("--limit", type=int, default=100, help="Max docs to load")
    args = parser.parse_args()

    store = DocumentStore()
    count = 0

    for doc in load_pubmed_jsonl(args.pubmed):
        if store.add(doc):
            count += 1
        if count >= args.limit:
            break

    if count < args.limit:
        for doc in load_textbooks_jsonl(args.textbooks):
            if store.add(doc):
                count += 1
            if count >= args.limit:
                break

    print(f"Loaded {len(store)} unique docs")


if __name__ == "__main__":
    main()
