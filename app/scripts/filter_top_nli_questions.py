from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from app.core.config import settings
from app.eval.nli_eval import _infer_nli
from app.schemas.response import QuestionItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
LOGGER = logging.getLogger(__name__)


def _default_output_path(input_path: str, top_n: int) -> Path:
    path = Path(input_path)
    return path.with_name(f"{path.stem}_top{top_n}_nli{path.suffix}")


def _default_summary_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}_summary.json")


def rank_questions_by_nli(
    input_path: str,
    *,
    model_name: str,
    max_length: int = 512,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {
        "total_seen": 0,
        "scored": 0,
        "invalid": 0,
        "skipped_status": 0,
        "skipped_no_evidence": 0,
    }

    with Path(input_path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue

            stats["total_seen"] += 1

            try:
                payload = json.loads(line)
                question = QuestionItem.model_validate(payload)
            except Exception:
                stats["invalid"] += 1
                continue

            if question.status != "OK":
                stats["skipped_status"] += 1
                continue

            evidence_text = " ".join(
                evidence.span_text for evidence in question.evidence if evidence.span_text
            ).strip()
            if not evidence_text:
                stats["skipped_no_evidence"] += 1
                continue

            answer_text = getattr(question.options, question.answer_key, "")
            hypothesis = f"{question.stem} {answer_text}".strip()
            scores = _infer_nli(
                evidence_text,
                hypothesis,
                model_name=model_name,
                max_length=max_length,
            )
            label = max(scores.items(), key=lambda item: item[1])[0]

            ranked.append(
                {
                    "line_number": line_number,
                    "topic": question.topic,
                    "competency": question.competency,
                    "stem": question.stem,
                    "answer_key": question.answer_key,
                    "answer_text": answer_text,
                    "entailment": scores.get("entailment", 0.0),
                    "neutral": scores.get("neutral", 0.0),
                    "contradiction": scores.get("contradiction", 0.0),
                    "label": label,
                    "payload": payload,
                }
            )
            stats["scored"] += 1

            if stats["total_seen"] % 50 == 0:
                LOGGER.info(
                    "Processed %d questions, scored %d so far",
                    stats["total_seen"],
                    stats["scored"],
                )

    ranked.sort(key=lambda item: (-item["entailment"], item["line_number"]))
    return ranked, stats


def write_ranked_jsonl(selected: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for item in selected:
            handle.write(json.dumps(item["payload"], ensure_ascii=False))
            handle.write("\n")


def write_summary(
    *,
    summary_path: Path,
    input_path: str,
    output_path: Path,
    model_name: str,
    requested_top_n: int,
    selected: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> None:
    entailments = [item["entailment"] for item in selected]
    summary = {
        "input_path": input_path,
        "output_path": str(output_path),
        "model": model_name,
        "requested_top_n": requested_top_n,
        "selected_count": len(selected),
        "cutoff_entailment": entailments[-1] if entailments else 0.0,
        "max_entailment": entailments[0] if entailments else 0.0,
        "avg_entailment_selected": (
            sum(entailments) / len(entailments) if entailments else 0.0
        ),
        **stats,
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter top-N questions by NLI entailment score."
    )
    parser.add_argument(
        "--input",
        default=settings.QUESTION_BANK_PATH,
        help="Path to input question_bank JSONL.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Path to output JSONL. Default follows input filename.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=650,
        help="How many highest-entailment questions to keep.",
    )
    parser.add_argument(
        "--summary-output",
        default="",
        help="Optional summary JSON path.",
    )
    parser.add_argument(
        "--model",
        default=settings.NLI_MODEL,
        help="Hugging Face NLI model name.",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=512,
        help="Tokenizer max length.",
    )
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else _default_output_path(args.input, args.top_n)
    summary_path = (
        Path(args.summary_output)
        if args.summary_output
        else _default_summary_path(output_path)
    )

    LOGGER.info("Scoring questions with NLI model: %s", args.model)
    ranked, stats = rank_questions_by_nli(
        args.input,
        model_name=args.model,
        max_length=args.max_length,
    )

    selected = ranked[: args.top_n]
    write_ranked_jsonl(selected, output_path)
    write_summary(
        summary_path=summary_path,
        input_path=args.input,
        output_path=output_path,
        model_name=args.model,
        requested_top_n=args.top_n,
        selected=selected,
        stats=stats,
    )

    LOGGER.info(
        "Saved %d/%d scored questions to %s",
        len(selected),
        stats["scored"],
        output_path,
    )
    LOGGER.info("Summary written to %s", summary_path)


if __name__ == "__main__":
    main()
