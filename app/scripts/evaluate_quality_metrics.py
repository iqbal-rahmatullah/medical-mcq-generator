"""
Quality Metrics Comparison for Cross-CoVe Ablation Study

Uses the same evaluation logic as the API endpoints.
"""

import argparse
import json
import logging
from typing import Dict, Any

from app.eval.rouge_eval import evaluate_question_bank
from app.eval.nli_eval import evaluate_question_bank_nli
from app.eval.semantic_eval import evaluate_question_bank_semantic
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
LOGGER = logging.getLogger(__name__)


def evaluate_jsonl(jsonl_path: str) -> Dict[str, Any]:
    """Evaluate a JSONL file using the standard evaluation functions."""
    
    # ROUGE evaluation
    LOGGER.info(f"Evaluating ROUGE for {jsonl_path}...")
    rouge_result = evaluate_question_bank(
        jsonl_path,
        limit=0,
        include_items=False,
    )
    
    # NLI evaluation
    LOGGER.info(f"Evaluating NLI for {jsonl_path}...")
    nli_result = evaluate_question_bank_nli(
        jsonl_path,
        model_name=settings.NLI_MODEL,
        limit=0,
        include_items=False,
    )
    
    # Semantic evaluation
    LOGGER.info(f"Evaluating Semantic for {jsonl_path}...")
    semantic_result = evaluate_question_bank_semantic(
        jsonl_path,
        model_name=settings.SEMANTIC_MODEL,
        limit=0,
        include_items=False,
    )
    
    return {
        "total": rouge_result.scored,
        "rouge1_f1": rouge_result.avg_rouge1_f1,
        "rougeL_f1": rouge_result.avg_rougeL_f1,
        "nli_entailment": nli_result.avg_entailment,
        "nli_labels": nli_result.label_counts,
        "semantic_similarity": semantic_result.avg_cosine,
        "semantic_categories": semantic_result.categories,
    }


def print_comparison(cove_on: Dict[str, Any], cove_off: Dict[str, Any]):
    """Print comparison table."""
    print("\n" + "=" * 80)
    print("QUALITY METRICS COMPARISON: Cross-CoVe ON vs OFF")
    print("=" * 80)
    
    print(f"\n{'Metric':<35} {'CoVe ON':<20} {'CoVe OFF':<20}")
    print("-" * 75)
    
    print(f"{'Total Questions Evaluated':<35} {cove_on['total']:<20} {cove_off['total']:<20}")
    
    rouge1_on = f"{cove_on['rouge1_f1']:.4f}"
    rouge1_off = f"{cove_off['rouge1_f1']:.4f}"
    print(f"{'ROUGE-1 F1':<35} {rouge1_on:<20} {rouge1_off:<20}")
    
    rougeL_on = f"{cove_on['rougeL_f1']:.4f}"
    rougeL_off = f"{cove_off['rougeL_f1']:.4f}"
    print(f"{'ROUGE-L F1':<35} {rougeL_on:<20} {rougeL_off:<20}")
    
    nli_on = f"{cove_on['nli_entailment']:.4f}"
    nli_off = f"{cove_off['nli_entailment']:.4f}"
    print(f"{'NLI Entailment Score':<35} {nli_on:<20} {nli_off:<20}")
    
    sem_on = f"{cove_on['semantic_similarity']:.4f}"
    sem_off = f"{cove_off['semantic_similarity']:.4f}"
    print(f"{'Semantic Similarity':<35} {sem_on:<20} {sem_off:<20}")
    
    # NLI Distribution
    print("\n" + "-" * 75)
    print("NLI LABEL DISTRIBUTION")
    print("-" * 75)
    on_labels = cove_on.get("nli_labels", {})
    off_labels = cove_off.get("nli_labels", {})
    for label in ["entailment", "neutral", "contradiction"]:
        on_count = on_labels.get(label, 0)
        off_count = off_labels.get(label, 0)
        print(f"{label.capitalize():<35} {on_count:<20} {off_count:<20}")
    
    # Semantic Categories
    print("\n" + "-" * 75)
    print("SEMANTIC SIMILARITY CATEGORIES")
    print("-" * 75)
    on_cats = cove_on.get("semantic_categories", {})
    off_cats = cove_off.get("semantic_categories", {})
    for cat in ["strong", "moderate", "weak", "very_weak"]:
        on_count = on_cats.get(cat, 0)
        off_count = off_cats.get(cat, 0)
        print(f"{cat.capitalize():<35} {on_count:<20} {off_count:<20}")
    
    # Interpretation
    print("\n" + "-" * 75)
    print("INTERPRETATION")
    print("-" * 75)
    
    rouge_diff = cove_on["rougeL_f1"] - cove_off["rougeL_f1"]
    nli_diff = cove_on["nli_entailment"] - cove_off["nli_entailment"]
    sem_diff = cove_on["semantic_similarity"] - cove_off["semantic_similarity"]
    
    if rouge_diff > 0:
        print(f"✓ ROUGE-L: CoVe ON lebih tinggi (+{rouge_diff:.4f})")
    else:
        print(f"○ ROUGE-L: CoVe OFF lebih tinggi ({rouge_diff:.4f})")
    
    if nli_diff > 0:
        print(f"✓ NLI Entailment: CoVe ON lebih tinggi (+{nli_diff:.4f})")
    else:
        print(f"○ NLI Entailment: CoVe OFF lebih tinggi ({nli_diff:.4f})")
    
    if sem_diff > 0:
        print(f"✓ Semantic Similarity: CoVe ON lebih tinggi (+{sem_diff:.4f})")
    else:
        print(f"○ Semantic Similarity: CoVe OFF lebih tinggi ({sem_diff:.4f})")
    
    print("=" * 80)


def save_results(cove_on: Dict[str, Any], cove_off: Dict[str, Any], output_path: str):
    """Save results to JSON."""
    results = {
        "cove_on": cove_on,
        "cove_off": cove_off,
    }
    
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    
    LOGGER.info(f"Results saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate Quality Metrics for Cross-CoVe Ablation")
    parser.add_argument(
        "--cove-on",
        type=str,
        default="data/ablation_cove_on.jsonl",
        help="Path to CoVe ON questions JSONL",
    )
    parser.add_argument(
        "--cove-off",
        type=str,
        default="data/ablation_cove_off.jsonl",
        help="Path to CoVe OFF questions JSONL",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/quality_metrics_comparison.json",
        help="Path to output JSON",
    )
    args = parser.parse_args()
    
    # Evaluate both files
    LOGGER.info("Evaluating CoVe ON questions...")
    cove_on_metrics = evaluate_jsonl(args.cove_on)
    
    LOGGER.info("Evaluating CoVe OFF questions...")
    cove_off_metrics = evaluate_jsonl(args.cove_off)
    
    # Print and save
    print_comparison(cove_on_metrics, cove_off_metrics)
    save_results(cove_on_metrics, cove_off_metrics, args.output)


if __name__ == "__main__":
    main()
