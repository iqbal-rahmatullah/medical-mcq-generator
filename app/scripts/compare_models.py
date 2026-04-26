from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.config import settings
from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.models import Document
from app.generation.evidence_format import render_evidence
from app.generation.llm_client import LLMClient
from app.retrieval.bm25 import BM25Index
from app.retrieval.query_builder import build_query

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger(__name__)

# Rate limit handling constants
MAX_RETRIES_PER_KEY = 2
INITIAL_BACKOFF_SEC = 5.0
MAX_BACKOFF_SEC = 30.0
RATE_LIMIT_KEYWORDS = ["rate", "limit", "429", "too many", "quota", "exceeded"]

# Cerebras API keys for rotation
CEREBRAS_API_KEYS = []

T = TypeVar("T")


def is_rate_limit_error(error: Exception) -> bool:
    error_str = str(error).lower()
    return any(keyword in error_str for keyword in RATE_LIMIT_KEYWORDS)


class CerebrasKeyRotator:
    """Manages multiple Cerebras API keys with automatic rotation on rate limit."""
    def __init__(self, api_keys: List[str]):
        self._api_keys = api_keys
        self._current_index = 0
        self._exhausted_keys: set = set()
    
    @property
    def current_key(self) -> str:
        return self._api_keys[self._current_index]
    
    @property
    def current_key_index(self) -> int:
        return self._current_index + 1
    
    @property
    def total_keys(self) -> int:
        return len(self._api_keys)
    
    def rotate(self) -> bool:
        """Rotate to next available key. Returns False if all keys exhausted."""
        self._exhausted_keys.add(self._current_index)
        
        # Find next non-exhausted key
        for i in range(len(self._api_keys)):
            next_idx = (self._current_index + 1 + i) % len(self._api_keys)
            if next_idx not in self._exhausted_keys:
                self._current_index = next_idx
                return True
        
        return False  # All keys exhausted
    
    def reset(self) -> None:
        """Reset exhausted keys for new request cycle."""
        self._exhausted_keys.clear()
    
    def create_client(self, model: str) -> LLMClient:
        """Create LLMClient with current API key."""
        return LLMClient(
            provider="cerebras",
            model=model,
            cerebras_api_key=self.current_key,
        )


# Global key rotator instance
_KEY_ROTATOR = CerebrasKeyRotator(CEREBRAS_API_KEYS)


def generate_with_fallback(
    model: str,
    topic: str,
    competency: str,
    evidence_text: str,
    max_retries_per_key: int = MAX_RETRIES_PER_KEY,
) -> Any:
    """
    Generate MCQ with automatic API key rotation on rate limit.
    
    Strategy:
    1. Try current key up to max_retries_per_key times with exponential backoff
    2. If still rate limited, rotate to next API key
    3. Repeat until success or all keys exhausted
    """
    _KEY_ROTATOR.reset()
    last_exception = None
    
    while True:
        client = _KEY_ROTATOR.create_client(model)
        
        for attempt in range(max_retries_per_key):
            try:
                result = client.generate_mcq(
                    topic=topic,
                    competency=competency,
                    evidence_text=evidence_text,
                    n_questions=1,
                )
                return result
                
            except Exception as e:
                last_exception = e
                
                if not is_rate_limit_error(e):
                    raise  # Non-rate-limit error, propagate immediately
                
                # Rate limit hit - try backoff first
                if attempt < max_retries_per_key - 1:
                    backoff = min(INITIAL_BACKOFF_SEC * (2 ** attempt), MAX_BACKOFF_SEC)
                    jitter = random.uniform(0, backoff * 0.1)
                    wait_time = backoff + jitter
                    
                    LOGGER.warning(
                        f"⚠️ Rate limit on key {_KEY_ROTATOR.current_key_index}/{_KEY_ROTATOR.total_keys} "
                        f"(attempt {attempt + 1}/{max_retries_per_key}). Waiting {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
        
        # Max retries on this key exhausted, try rotating
        if _KEY_ROTATOR.rotate():
            LOGGER.info(
                f"🔄 Rotating to API key {_KEY_ROTATOR.current_key_index}/{_KEY_ROTATOR.total_keys}"
            )
            time.sleep(1.0)  # Brief pause before using new key
        else:
            LOGGER.error("❌ All API keys exhausted!")
            raise last_exception

TEST_CASES = [
    ("Hypertension", "Diagnosis"),
    ("Diabetes Mellitus", "Treatment"),
    ("Myocardial Infarction", "Etiology"),
    ("Pneumonia", "Diagnosis"),
    ("Asthma", "Treatment"),
    ("Stroke", "Pathophysiology"),
    ("Heart Failure", "Pharmacology"),
    ("Tuberculosis", "Prevention"),
    ("HIV", "Screening"),
    ("Chronic Kidney Disease", "Monitoring"),
    ("Systemic Lupus Erythematosus", "Diagnosis"),
    ("Preeclampsia", "Treatment"),
    ("Neonatal Sepsis", "Etiology"),
    ("Atrial Fibrillation", "Complications"),
    ("Deep Vein Thrombosis", "Prevention"),
    ("Depression", "Pharmacology"),
    ("Epilepsy", "Prognosis"),
    ("Colorectal Cancer", "Screening"),
    ("Rheumatoid Arthritis", "Pathophysiology"),
    ("Obesity", "Investigation"),
]

MODELS: Dict[str, Dict[str, str]] = {
    "gpt-oss-120b": {
        "provider": "cerebras",
        "model": "gpt-oss-120b",
        "params": "120B",
    },
    "llama-3.3-70b": {
        "provider": "cerebras",
        "model": "llama-3.3-70b",
        "params": "70B",
    },
    "qwen-3-32b": {
        "provider": "cerebras",
        "model": "qwen-3-32b",
        "params": "32B",
    },
    "llama3.1-8b": {
        "provider": "cerebras",
        "model": "llama3.1-8b",
        "params": "8B",
    },
}

@dataclass
class SingleResult:
    topic: str
    competency: str
    success: bool
    status: str
    latency_sec: float
    rouge_l: Optional[float] = None
    nli_entailment: Optional[float] = None
    semantic_cosine: Optional[float] = None
    stem_preview: Optional[str] = None
    error: Optional[str] = None


@dataclass
class ModelResult:
    model_name: str
    model_id: str
    params: str
    total_cases: int
    success_count: int
    success_rate: float
    json_parse_count: int
    json_parse_rate: float
    avg_rouge_l: float
    avg_nli_entailment: float
    avg_semantic_cosine: float
    avg_latency_sec: float
    composite_score: float
    individual_results: List[SingleResult] = field(default_factory=list)



import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


def _lcs_length(a_tokens: List[str], b_tokens: List[str]) -> int:
    if not a_tokens or not b_tokens:
        return 0
    prev = [0] * (len(b_tokens) + 1)
    for token in a_tokens:
        curr = [0]
        for j, b_token in enumerate(b_tokens, start=1):
            if token == b_token:
                curr.append(prev[j - 1] + 1)
            else:
                curr.append(max(curr[-1], prev[j]))
        prev = curr
    return prev[-1]


def rouge_l_f1(candidate: str, reference: str) -> float:
    """Calculate ROUGE-L F1 score"""
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0
    lcs = _lcs_length(cand_tokens, ref_tokens)
    precision = lcs / len(cand_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)

_BM25_INDEX: Optional[BM25Index] = None
_DOCUMENTS: List[Document] = []


def load_corpus(max_docs: int = 2000) -> None:
    global _DOCUMENTS, _BM25_INDEX
    
    LOGGER.info("Loading corpus...")
    docs = []
    
    # Load PubMed
    for i, doc in enumerate(load_pubmed_hf(
        settings.CORPUS_PUBMED_HF_DATASET,
        local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
        streaming=settings.CORPUS_HF_STREAMING,
    )):
        docs.append(doc)
        if i + 1 >= max_docs:
            break
    
    LOGGER.info(f"Loaded {len(docs)} documents")
    _DOCUMENTS = docs
    
    # Build BM25 index
    LOGGER.info("Building BM25 index...")
    _BM25_INDEX = BM25Index.build(docs)
    LOGGER.info("Retriever ready")


def retrieve_evidence(topic: str, competency: str, top_k: int = 5) -> List[Document]:
    if _BM25_INDEX is None:
        raise RuntimeError("Corpus not loaded. Call load_corpus() first.")
    
    query = build_query(topic, competency)
    results = _BM25_INDEX.search(query, top_k=top_k)
    return [doc for doc, _ in results]



def run_single_test(
    model: str,
    topic: str,
    competency: str,
    evidence_docs: List[Document],
) -> SingleResult:
    """Run a single MCQ generation test with API key rotation fallback"""
    start_time = time.time()
    
    try:
        evidence_text = render_evidence(
            evidence_docs,
            max_chars_per_doc=settings.EVIDENCE_MAX_CHARS_PER_DOC,
            max_total_chars=settings.EVIDENCE_MAX_TOTAL_CHARS,
        )
        
        # Use generate_with_fallback for API key rotation
        mcq_items = generate_with_fallback(
            model=model,
            topic=topic,
            competency=competency,
            evidence_text=evidence_text,
        )
        
        latency = time.time() - start_time
        
        if not mcq_items:
            return SingleResult(
                topic=topic,
                competency=competency,
                success=False,
                status="EMPTY_RESPONSE",
                latency_sec=latency,
                error="No MCQ items returned",
            )
        
        q = mcq_items[0]
        success = q.status == "OK"
        
        # Calculate ROUGE-L if successful
        rouge_l = None
        if success:
            answer_text = getattr(q.options, q.answer_key, "")
            combined = f"{q.stem} {answer_text}"
            rouge_l = rouge_l_f1(combined, evidence_text)
        
        return SingleResult(
            topic=topic,
            competency=competency,
            success=success,
            status=q.status,
            latency_sec=latency,
            rouge_l=rouge_l,
            stem_preview=q.stem[:100] if q.stem else None,
        )
        
    except Exception as e:
        return SingleResult(
            topic=topic,
            competency=competency,
            success=False,
            status="ERROR",
            latency_sec=time.time() - start_time,
            error=str(e),
        )


def run_model_experiment(
    model_name: str,
    config: Dict[str, str],
    test_cases: List[tuple],
    sleep_between: float = 2.0,
) -> ModelResult:
    """Run experiment for a single model with API key rotation"""
    LOGGER.info(f"\n{'='*60}")
    LOGGER.info(f"Running experiment: {model_name} ({config['params']})")
    LOGGER.info(f"Using {len(CEREBRAS_API_KEYS)} API keys with rotation")
    LOGGER.info(f"{'='*60}")
    
    model_id = config["model"]
    results: List[SingleResult] = []
    
    for i, (topic, competency) in enumerate(test_cases, 1):
        LOGGER.info(f"[{i}/{len(test_cases)}] {topic} - {competency}")
        
        # Retrieve evidence
        evidence_docs = retrieve_evidence(topic, competency, top_k=5)
        
        # Run test with API key rotation
        result = run_single_test(model_id, topic, competency, evidence_docs)
        results.append(result)
        
        status_icon = "✅" if result.success else "❌"
        LOGGER.info(f"  {status_icon} {result.status} | {result.latency_sec:.2f}s")
        
        # Rate limiting - sleep between requests
        if i < len(test_cases):
            time.sleep(sleep_between)
    
    # Calculate aggregates
    success_count = sum(1 for r in results if r.success)
    json_parse_count = sum(1 for r in results if r.status != "ERROR")
    rouge_scores = [r.rouge_l for r in results if r.rouge_l is not None]
    latencies = [r.latency_sec for r in results]
    
    success_rate = success_count / len(test_cases)
    json_parse_rate = json_parse_count / len(test_cases)
    avg_rouge = sum(rouge_scores) / len(rouge_scores) if rouge_scores else 0.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    
    # Composite score (simplified - NLI and Semantic not computed for speed)
    # Using: 0.40 * success_rate + 0.40 * rouge + 0.20 * json_parse_rate
    composite = (0.40 * success_rate) + (0.40 * avg_rouge) + (0.20 * json_parse_rate)
    
    return ModelResult(
        model_name=model_name,
        model_id=config["model"],
        params=config["params"],
        total_cases=len(test_cases),
        success_count=success_count,
        success_rate=success_rate,
        json_parse_count=json_parse_count,
        json_parse_rate=json_parse_rate,
        avg_rouge_l=avg_rouge,
        avg_nli_entailment=0.0,  # Not computed for speed
        avg_semantic_cosine=0.0,  # Not computed for speed
        avg_latency_sec=avg_latency,
        composite_score=composite,
        individual_results=results,
    )


def print_summary(all_results: List[ModelResult]) -> None:
    """Print comparison summary table"""
    print("\n" + "=" * 80)
    print("MODEL COMPARISON RESULTS")
    print("=" * 80)
    
    # Sort by composite score
    sorted_results = sorted(all_results, key=lambda x: x.composite_score, reverse=True)
    
    print(f"\n{'Model':<20} {'Params':<8} {'Success%':<10} {'ROUGE-L':<10} {'Latency':<10} {'Composite':<10}")
    print("-" * 78)
    
    for i, r in enumerate(sorted_results, 1):
        rank = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else "  "))
        print(
            f"{rank}{r.model_name:<18} "
            f"{r.params:<8} "
            f"{r.success_rate*100:>6.1f}%    "
            f"{r.avg_rouge_l:>6.3f}    "
            f"{r.avg_latency_sec:>6.2f}s   "
            f"{r.composite_score:>6.3f}"
        )
    
    print("-" * 78)
    print(f"\n🏆 Best Model: {sorted_results[0].model_name} (Composite: {sorted_results[0].composite_score:.3f})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare LLM models for MCQ generation")
    parser.add_argument(
        "--output",
        type=str,
        default="model_comparison_results.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(MODELS.keys()),
        choices=list(MODELS.keys()),
        help="Models to compare",
    )
    parser.add_argument(
        "--test-cases",
        type=int,
        default=20,
        help="Number of test cases to run (max 20)",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=2000,
        help="Maximum corpus documents to load",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=2.0,
        help="Sleep between requests (rate limiting)",
    )
    
    args = parser.parse_args()
    
    # Limit test cases
    num_cases = min(args.test_cases, len(TEST_CASES))
    test_cases = TEST_CASES[:num_cases]
    
    print(f"\n📊 Model Comparison Experiment")
    print(f"   Models: {', '.join(args.models)}")
    print(f"   Test cases: {num_cases}")
    print(f"   Output: {args.output}\n")
    
    # Load corpus
    load_corpus(args.max_docs)
    
    # Run experiments
    all_results: List[ModelResult] = []
    
    for model_name in args.models:
        if model_name not in MODELS:
            LOGGER.warning(f"Unknown model: {model_name}, skipping")
            continue
        
        result = run_model_experiment(
            model_name,
            MODELS[model_name],
            test_cases,
            sleep_between=args.sleep,
        )
        all_results.append(result)
    
    # Print summary
    print_summary(all_results)
    
    # Save results
    output_data = {
        "experiment_info": {
            "models": args.models,
            "test_cases_count": num_cases,
            "corpus_docs": args.max_docs,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "results": [asdict(r) for r in all_results],
    }
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {args.output}")


if __name__ == "__main__":
    main()
