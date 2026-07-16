from __future__ import annotations

import argparse
import json
import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from app.core.config import settings
from app.schemas.request import GenerateRequestItem
from app.schemas.response import QuestionItem
from app.services import pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)

TEST_CASES = [
    {"topic": "Core concepts", "competency": "Definition"},
    {"topic": "Core concepts", "competency": "Application"},
    {"topic": "Key terminology", "competency": "Comparison"},
    {"topic": "Key terminology", "competency": "Definition"},
    {"topic": "Main processes", "competency": "Process steps"},
    {"topic": "Main processes", "competency": "Cause and effect"},
    {"topic": "Common issues", "competency": "Best practice"},
    {"topic": "Common issues", "competency": "Common mistakes"},
    {"topic": "Advanced topics", "competency": "Cause and effect"},
    {"topic": "Advanced topics", "competency": "Process steps"},
]


@dataclass
class AblationResult:
    mode: str
    total_generated: int
    status_ok: int
    status_failed_verification: int
    status_insufficient_evidence: int
    success_rate: float
    avg_runtime_ms: float
    reviewer_agreement_rate: float
    evidence_support_rate: float


@dataclass
class AblationSummary:
    cove_enabled: AblationResult
    cove_disabled: AblationResult
    filtering_rate: float  # How many were filtered by CoVe
    quality_improvement: float  # Difference in success rate
    cove_on_questions: List[QuestionItem] = None
    cove_off_questions: List[QuestionItem] = None


def _reset_pipeline(kb_id: str) -> None:
    """Reset pipeline state between runs."""
    pipeline.invalidate_retriever_cache(kb_id)
    pipeline._LLM_CLIENT = None


def _compute_metrics(questions: List[QuestionItem], mode: str) -> AblationResult:
    """Compute metrics for a set of generated questions."""
    total = len(questions)
    if total == 0:
        return AblationResult(
            mode=mode,
            total_generated=0,
            status_ok=0,
            status_failed_verification=0,
            status_insufficient_evidence=0,
            success_rate=0.0,
            avg_runtime_ms=0.0,
            reviewer_agreement_rate=0.0,
            evidence_support_rate=0.0,
        )
    
    status_ok = sum(1 for q in questions if q.status == "OK")
    status_failed = sum(1 for q in questions if q.status == "FAILED_VERIFICATION")
    status_insufficient = sum(1 for q in questions if q.status == "INSUFFICIENT_EVIDENCE")
    
    # Compute runtime
    runtimes = []
    for q in questions:
        timings = q.meta.timings_ms or {}
        total_ms = sum(float(timings.get(k, 0)) for k in ["retrieval", "llm", "verification"])
        runtimes.append(total_ms)
    avg_runtime = sum(runtimes) / len(runtimes) if runtimes else 0.0
    
    # Compute reviewer agreement (from gate metadata)
    reviewer_agreed = 0
    evidence_supported = 0
    for q in questions:
        gate = (q.meta.verification or {}).get("gate", {})
        failed_checks = gate.get("failed_checks", []) or []
        
        # Reviewer agreed if no reviewer_* failures
        if not any(c.startswith("reviewer_") for c in failed_checks):
            reviewer_agreed += 1
        
        # Evidence supported if gate passed
        if gate.get("pass"):
            evidence_supported += 1
    
    return AblationResult(
        mode=mode,
        total_generated=total,
        status_ok=status_ok,
        status_failed_verification=status_failed,
        status_insufficient_evidence=status_insufficient,
        success_rate=status_ok / total,
        avg_runtime_ms=avg_runtime,
        reviewer_agreement_rate=reviewer_agreed / total,
        evidence_support_rate=evidence_supported / total,
    )


def run_with_cove(payload: List[GenerateRequestItem], kb_id: str) -> List[QuestionItem]:
    """Run generation with Cross-CoVe enabled, capturing ALL questions (including failed)."""
    LOGGER.info("Running with Cross-CoVe ENABLED...")

    _reset_pipeline(kb_id)
    
    # Disable OK_ONLY_MODE to capture all questions
    original_ok_only = settings.OK_ONLY_MODE
    object.__setattr__(settings, 'OK_ONLY_MODE', False)
    
    try:
        results: List[QuestionItem] = []
        for event in pipeline.run_pipeline_stream(payload, include_failed=True):
            if event.get("type") == "question":
                results.append(QuestionItem.model_validate(event["question"]))
            elif event.get("type") == "question_failed":
                # Also capture failed questions
                q_data = event.get("question")
                if q_data:
                    results.append(QuestionItem.model_validate(q_data))
        return results
    finally:
        object.__setattr__(settings, 'OK_ONLY_MODE', original_ok_only)


def run_without_cove(payload: List[GenerateRequestItem], kb_id: str) -> List[QuestionItem]:
    """Run generation with Cross-CoVe disabled, capturing ALL questions."""
    LOGGER.info("Running with Cross-CoVe DISABLED...")

    # Monkey-patch both reviewer functions to skip verification entirely
    original_cross_cove = pipeline._get_cross_cove_reviewer
    original_reviewer = pipeline._get_reviewer_client
    original_ok_only = settings.OK_ONLY_MODE

    pipeline._get_cross_cove_reviewer = lambda: None
    pipeline._get_reviewer_client = lambda: None
    object.__setattr__(settings, 'OK_ONLY_MODE', False)

    try:
        _reset_pipeline(kb_id)
        results: List[QuestionItem] = []
        for event in pipeline.run_pipeline_stream(payload, include_failed=True):
            if event.get("type") == "question":
                results.append(QuestionItem.model_validate(event["question"]))
            elif event.get("type") == "question_failed":
                q_data = event.get("question")
                if q_data:
                    results.append(QuestionItem.model_validate(q_data))
        return results
    finally:
        # Restore original functions
        pipeline._get_cross_cove_reviewer = original_cross_cove
        pipeline._get_reviewer_client = original_reviewer
        object.__setattr__(settings, 'OK_ONLY_MODE', original_ok_only)
        _reset_pipeline(kb_id)  # Reset again to get reviewer back


def run_ablation(kb_id: str, n_questions_per_topic: int = 5) -> AblationSummary:
    """Run the full ablation study."""

    # Build payload
    payload = [
        GenerateRequestItem(
            kb_id=kb_id,
            topic=tc["topic"],
            competency=tc["competency"],
            n_questions=n_questions_per_topic,
        )
        for tc in TEST_CASES
    ]

    total_expected = len(TEST_CASES) * n_questions_per_topic
    LOGGER.info(f"Running ablation study with {total_expected} questions...")

    # Run with CoVe
    start = time.perf_counter()
    cove_results = run_with_cove(payload, kb_id)
    cove_time = (time.perf_counter() - start) * 1000
    LOGGER.info(f"Cross-CoVe ENABLED: {len(cove_results)} questions in {cove_time:.1f}ms")

    # Run without CoVe
    start = time.perf_counter()
    no_cove_results = run_without_cove(payload, kb_id)
    no_cove_time = (time.perf_counter() - start) * 1000
    LOGGER.info(f"Cross-CoVe DISABLED: {len(no_cove_results)} questions in {no_cove_time:.1f}ms")
    
    # Compute metrics
    cove_metrics = _compute_metrics(cove_results, "cove_enabled")
    no_cove_metrics = _compute_metrics(no_cove_results, "cove_disabled")
    
    # Compute comparison
    filtering_rate = 1.0 - (cove_metrics.status_ok / max(no_cove_metrics.status_ok, 1))
    quality_diff = cove_metrics.success_rate - no_cove_metrics.success_rate
    
    return AblationSummary(
        cove_enabled=cove_metrics,
        cove_disabled=no_cove_metrics,
        filtering_rate=max(0, filtering_rate),
        quality_improvement=quality_diff,
        cove_on_questions=cove_results,
        cove_off_questions=no_cove_results,
    )


def print_results(summary: AblationSummary) -> None:
    """Print ablation results in a formatted table."""
    print("\n" + "=" * 80)
    print("CROSS-COVE ABLATION STUDY RESULTS")
    print("=" * 80)
    
    print(f"\n{'Metric':<35} {'CoVe ON':<20} {'CoVe OFF':<20}")
    print("-" * 75)
    
    on = summary.cove_enabled
    off = summary.cove_disabled
    
    print(f"{'Total Generated':<35} {on.total_generated:<20} {off.total_generated:<20}")
    print(f"{'Status OK (Passed)':<35} {on.status_ok:<20} {off.status_ok:<20}")
    print(f"{'Status FAILED_VERIFICATION':<35} {on.status_failed_verification:<20} {off.status_failed_verification:<20}")
    print(f"{'Status INSUFFICIENT_EVIDENCE':<35} {on.status_insufficient_evidence:<20} {off.status_insufficient_evidence:<20}")
    print(f"{'Pass Rate':<35} {f'{on.success_rate:.2%}':<20} {f'{off.success_rate:.2%}':<20}")
    print(f"{'Avg Runtime (ms)':<35} {f'{on.avg_runtime_ms:.1f}':<20} {f'{off.avg_runtime_ms:.1f}':<20}")
    
    # Key metrics interpretation
    print("\n" + "-" * 75)
    print("CROSS-COVE EFFECTIVENESS ANALYSIS")
    print("-" * 75)
    
    # Questions rejected by CoVe
    rejected = on.status_failed_verification + on.status_insufficient_evidence
    print(f"{'Questions Rejected by CoVe':<35} {rejected} ({summary.filtering_rate:.2%})")
    
    # Runtime overhead
    if off.avg_runtime_ms > 0:
        overhead = ((on.avg_runtime_ms - off.avg_runtime_ms) / off.avg_runtime_ms) * 100
        print(f"{'Runtime Overhead':<35} {overhead:+.1f}%")
    
    # Interpretation
    print("\n" + "-" * 75)
    print("INTERPRETATION")
    print("-" * 75)
    if rejected > 0:
        print(f"✓ Cross-CoVe berhasil memfilter {rejected} soal ({summary.filtering_rate:.1%}) yang tidak valid")
        print(f"✓ Tanpa Cross-CoVe, {rejected} soal bermasalah akan masuk question bank")
    else:
        print("✓ Semua soal lolos verifikasi Cross-CoVe")
    
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-CoVe Ablation Study")
    parser.add_argument(
        "--kb-id",
        type=str,
        required=True,
        help="Knowledge base id to generate from (see GET /knowledge for ids). "
        "TEST_CASES topics should match content in this KB.",
    )
    parser.add_argument(
        "--n-questions",
        type=int,
        default=5,
        help="Number of questions per topic (default: 5)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/cove_ablation_results.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    summary = run_ablation(args.kb_id, args.n_questions)
    print_results(summary)
    
    # Save to JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "cove_enabled": asdict(summary.cove_enabled),
        "cove_disabled": asdict(summary.cove_disabled),
        "filtering_rate": summary.filtering_rate,
        "quality_improvement": summary.quality_improvement,
    }
    
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    
    LOGGER.info(f"Results saved to {output_path}")
    
    # Save questions to separate JSONL files
    cove_on_path = output_path.parent / "ablation_cove_on.jsonl"
    cove_off_path = output_path.parent / "ablation_cove_off.jsonl"
    
    if summary.cove_on_questions:
        with cove_on_path.open("w", encoding="utf-8") as f:
            for q in summary.cove_on_questions:
                f.write(json.dumps(q.model_dump(), ensure_ascii=False) + "\n")
        LOGGER.info(f"CoVe ON questions saved to {cove_on_path}")
    
    if summary.cove_off_questions:
        with cove_off_path.open("w", encoding="utf-8") as f:
            for q in summary.cove_off_questions:
                f.write(json.dumps(q.model_dump(), ensure_ascii=False) + "\n")
        LOGGER.info(f"CoVe OFF questions saved to {cove_off_path}")


if __name__ == "__main__":
    main()
