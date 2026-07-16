"""
Cross-CoVe Detection Rate Test

Tests how well Cross-CoVe can detect questions with intentionally wrong answers.
This validates the effectiveness of the verification mechanism.
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass
from typing import List, Dict, Any

from app.schemas.response import QuestionItem
from app.services import pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    question_id: int
    topic: str
    original_answer: str
    wrong_answer: str
    detected: bool
    cove_decision: str
    votes: List[str]


def load_test_questions(path: str) -> List[Dict[str, Any]]:
    """Load questions with wrong answers."""
    with open(path, "r") as f:
        return json.load(f)


def run_detection_test(
    questions: List[Dict[str, Any]],
    max_questions: int = None
) -> List[DetectionResult]:
    """Run Cross-CoVe verification on questions with wrong answers."""
    
    # Initialize Cross-CoVe reviewer using pipeline helper
    reviewer = pipeline._get_cross_cove_reviewer()
    if reviewer is None:
        LOGGER.error("Failed to initialize Cross-CoVe reviewer. Check settings.")
        return []
    
    LOGGER.info(f"Cross-CoVe initialized with {len(reviewer._reviewers)} reviewers")
    
    if max_questions:
        questions = questions[:max_questions]
    
    results: List[DetectionResult] = []
    detected_count = 0
    
    for i, q_data in enumerate(questions, start=1):
        topic = q_data.get("topic", "Unknown")
        original_answer = q_data.get("original_answer", "?")
        wrong_answer = q_data.get("answer_key", "?")
        
        LOGGER.info(f"\n[{i}/{len(questions)}] Testing: {topic}")
        LOGGER.info(f"  Original: {original_answer} → Wrong: {wrong_answer}")
        
        try:
            # Create QuestionItem
            question = QuestionItem.model_validate(q_data)
            
            # Build evidence text from evidence_spans
            evidence_text = ""
            for span in q_data.get("evidence_spans", []):
                evidence_text += span.get("text", "") + "\n\n"
            
            if not evidence_text:
                evidence_text = f"Topic: {topic}"
            
            # Run Cross-CoVe verification
            decision = reviewer.cross_verify(question, evidence_text)
            
            # Get vote details from last verification
            votes = getattr(reviewer, '_last_votes', [])
            
            # Check if detected (decision != wrong_answer means detected as wrong)
            detected = (decision != wrong_answer)
            
            if detected:
                detected_count += 1
                LOGGER.info(f"  ✓ DETECTED! CoVe decision: {decision} (expected wrong: {wrong_answer})")
            else:
                LOGGER.warning(f"  ✗ MISSED! CoVe agreed with wrong answer: {decision}")
            
            results.append(DetectionResult(
                question_id=i,
                topic=topic,
                original_answer=original_answer,
                wrong_answer=wrong_answer,
                detected=detected,
                cove_decision=decision if decision else "INSUFFICIENT",
                votes=votes,
            ))
            
        except Exception as e:
            LOGGER.error(f"  Error: {e}")
            results.append(DetectionResult(
                question_id=i,
                topic=topic,
                original_answer=original_answer,
                wrong_answer=wrong_answer,
                detected=False,
                cove_decision="ERROR",
                votes=[],
            ))
    
    return results


def print_report(results: List[DetectionResult]):
    """Print detection test report."""
    print("\n" + "=" * 80)
    print("CROSS-COVE DETECTION RATE TEST RESULTS")
    print("=" * 80)
    
    total = len(results)
    detected = sum(1 for r in results if r.detected)
    missed = total - detected
    detection_rate = detected / total * 100 if total > 0 else 0
    
    print(f"\nTotal Questions Tested:     {total}")
    print(f"Detected as Wrong:          {detected} ({detection_rate:.1f}%)")
    print(f"Missed (False Negative):    {missed} ({100-detection_rate:.1f}%)")
    
    print("\n" + "-" * 80)
    print("DETECTION RATE BY TOPIC")
    print("-" * 80)
    
    # Group by topic
    topic_stats: Dict[str, Dict[str, int]] = {}
    for r in results:
        if r.topic not in topic_stats:
            topic_stats[r.topic] = {"total": 0, "detected": 0}
        topic_stats[r.topic]["total"] += 1
        if r.detected:
            topic_stats[r.topic]["detected"] += 1
    
    for topic, stats in sorted(topic_stats.items()):
        rate = stats["detected"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {topic:<35} {stats['detected']}/{stats['total']} ({rate:.0f}%)")
    
    print("\n" + "-" * 80)
    print("INTERPRETATION")
    print("-" * 80)
    
    if detection_rate >= 80:
        print(f"✓ EXCELLENT: Cross-CoVe berhasil mendeteksi {detection_rate:.1f}% soal dengan jawaban salah")
    elif detection_rate >= 60:
        print(f"○ GOOD: Cross-CoVe mendeteksi {detection_rate:.1f}% soal salah, masih ada ruang perbaikan")
    else:
        print(f"✗ NEEDS IMPROVEMENT: Hanya {detection_rate:.1f}% terdeteksi, perlu evaluasi mekanisme")
    
    print("=" * 80)


def save_results(results: List[DetectionResult], output_path: str):
    """Save results to JSON."""
    output_data = {
        "summary": {
            "total": len(results),
            "detected": sum(1 for r in results if r.detected),
            "detection_rate": sum(1 for r in results if r.detected) / len(results) * 100 if results else 0,
        },
        "details": [
            {
                "question_id": r.question_id,
                "topic": r.topic,
                "original_answer": r.original_answer,
                "wrong_answer": r.wrong_answer,
                "detected": r.detected,
                "cove_decision": r.cove_decision,
                "votes": r.votes,
            }
            for r in results
        ]
    }
    
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    
    LOGGER.info(f"Results saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Cross-CoVe Detection Rate Test")
    parser.add_argument(
        "--input",
        type=str,
        default="data/test_wrong_answers.json",
        help="Path to test questions with wrong answers",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/cove_detection_results.json",
        help="Path to output results",
    )
    parser.add_argument(
        "--max-questions",
        type=int,
        default=None,
        help="Maximum number of questions to test (default: all)",
    )
    args = parser.parse_args()
    
    # Load test questions
    LOGGER.info(f"Loading test questions from {args.input}...")
    questions = load_test_questions(args.input)
    LOGGER.info(f"Loaded {len(questions)} questions with wrong answers")
    
    # Run detection test
    start = time.perf_counter()
    results = run_detection_test(questions, args.max_questions)
    elapsed = time.perf_counter() - start
    
    LOGGER.info(f"Test completed in {elapsed:.1f}s")
    
    # Print and save results
    print_report(results)
    save_results(results, args.output)


if __name__ == "__main__":
    main()
