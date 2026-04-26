from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _build_key(item: dict, mode: str) -> str:
    stem = _normalize(str(item.get("stem", "")))
    topic = _normalize(str(item.get("topic", "")))
    competency = _normalize(str(item.get("competency", "")))

    if mode == "stem":
        return stem
    if mode == "stem+topic":
        return f"{topic}||{stem}"
    if mode == "stem+topic+competency":
        return f"{topic}||{competency}||{stem}"
    return stem


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        default="app/logging/question_bank.jsonl",
        help="Path to question_bank.jsonl",
    )
    parser.add_argument(
        "--mode",
        choices=["stem", "stem+topic", "stem+topic+competency"],
        default="stem",
        help="Duplicate key mode",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON file for duplicate groups",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max duplicate groups to show (0 = all)",
    )
    parser.add_argument(
        "--show",
        type=int,
        default=3,
        help="Number of items to show per duplicate group",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    groups: Dict[str, List[dict]] = defaultdict(list)
    total = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = _build_key(item, args.mode)
            if key:
                groups[key].append(item)

    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    duplicate_count = len(duplicates)
    duplicate_items = sum(len(v) for v in duplicates.values())

    print(f"Total items: {total}")
    print(f"Duplicate groups: {duplicate_count}")
    print(f"Duplicate items (including originals): {duplicate_items}")

    shown = 0
    for key, items in sorted(duplicates.items(), key=lambda kv: len(kv[1]), reverse=True):
        if args.limit and shown >= args.limit:
            break
        shown += 1
        print("-" * 60)
        print(f"Group {shown} | count={len(items)} | key={key}")
        for idx, item in enumerate(items[: args.show], start=1):
            print(f"  {idx}. {item.get('stem', '').strip()}")

    if args.output:
        output_path = Path(args.output)
        payload = [
            {
                "key": key,
                "count": len(items),
                "items": items,
            }
            for key, items in duplicates.items()
        ]
        output_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2))
        print(f"Duplicate report saved to: {output_path}")


if __name__ == "__main__":
    main()
