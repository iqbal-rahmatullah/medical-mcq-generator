#!/usr/bin/env python3
"""
Competency Discovery Tool - Data-Driven Approach

Discover medical competencies from dataset based on keyword frequency,
without relying on pre-defined competency lists.

This tool:
1. Extracts top medical keywords from the dataset
2. Identifies common medical term patterns
3. Suggests potential competencies based on data
4. Provides evidence for competency selection

Usage:
    python app/scripts/discover_competencies.py --max-docs 5000 --top-keywords 100
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.models import Document
from app.core.config import settings


# Medical term patterns for categorization
MEDICAL_PATTERNS = {
    "diagnostic": [
        r"\bdiagnos(is|tic|e)\b",
        r"\bsymptom(s)?\b",
        r"\bsign(s)?\b",
        r"\bscreen(ing)?\b",
        r"\btest(ing|s)?\b",
        r"\bevaluat(ion|e)\b",
        r"\bexaminat(ion)?\b",
        r"\bassessment\b",
        r"\bidentif(y|ication)\b",
    ],
    "treatment": [
        r"\btreat(ment|ed|ing)?\b",
        r"\btherap(y|ies|eutic)\b",
        r"\bdrug(s)?\b",
        r"\bmedication(s)?\b",
        r"\bdosage\b",
        r"\bmanage(ment|d)?\b",
        r"\bintervent(ion|ions)\b",
        r"\bsurg(ery|ical)\b",
    ],
    "causation": [
        r"\bcause(s|d)?\b",
        r"\betiology\b",
        r"\brisk\s+factor(s)?\b",
        r"\bpathogen(esis)?\b",
        r"\bmechanism(s)?\b",
        r"\bassociated\s+with\b",
        r"\bleads?\s+to\b",
    ],
    "prevention": [
        r"\bprevent(ion|ive|ed)?\b",
        r"\bprophyla(xis|ctic)\b",
        r"\bvaccinat(ion|e)\b",
        r"\brisk\s+reduction\b",
        r"\bscreening\b",
    ],
    "outcome": [
        r"\bprognos(is|tic)\b",
        r"\boutcome(s)?\b",
        r"\bmortalit(y)?\b",
        r"\bsurvival\b",
        r"\bcomplicat(ion|ions)\b",
        r"\brecurren(ce|t)\b",
    ],
    "investigation": [
        r"\bimaging\b",
        r"\blaboratory\b",
        r"\blab(s)?\b",
        r"\bbiomarker(s)?\b",
        r"\btest(ing|s)?\b",
        r"\bradiology\b",
        r"\bpathology\b",
    ],
    "pharmacology": [
        r"\bpharmacolog(y|ical)\b",
        r"\bpharmacokinetic(s)?\b",
        r"\badverse\s+effect(s)?\b",
        r"\bside\s+effect(s)?\b",
        r"\bdrug\s+interaction(s)?\b",
        r"\btoxicit(y)?\b",
        r"\bcontraindication(s)?\b",
    ],
    "monitoring": [
        r"\bmonitor(ing|ed)?\b",
        r"\bfollow[- ]up\b",
        r"\btracking\b",
        r"\bsurveillance\b",
        r"\brespon(se|d)\b",
    ],
}


def load_documents(max_docs: int = 0) -> List[Document]:
    """Load documents from both sources"""
    docs = []
    
    print(f"📥 Loading PubMed documents...")
    pubmed_limit = max_docs if max_docs > 0 else settings.CORPUS_PUBMED_MAX_DOCS
    for i, doc in enumerate(load_pubmed_hf(
        settings.CORPUS_PUBMED_HF_DATASET,
        local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
        streaming=settings.CORPUS_HF_STREAMING,
    )):
        docs.append(doc)
        if pubmed_limit and i + 1 >= pubmed_limit:
            break
    print(f"✅ Loaded {len(docs)} PubMed documents")
    
    start_idx = len(docs)
    print(f"📥 Loading Textbooks documents...")
    textbook_limit = max_docs if max_docs > 0 else settings.CORPUS_TEXTBOOKS_MAX_DOCS
    for i, doc in enumerate(load_textbooks_hf(
        settings.CORPUS_TEXTBOOKS_HF_DATASET,
        local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
        streaming=settings.CORPUS_HF_STREAMING,
    )):
        docs.append(doc)
        if textbook_limit and i + 1 >= textbook_limit:
            break
    print(f"✅ Loaded {len(docs) - start_idx} Textbooks documents\n")
    
    return docs


def extract_medical_keywords(
    docs: List[Document],
    min_length: int = 4,
    stopwords: Set[str] = None
) -> Counter:
    """
    Extract medical keywords from documents
    
    Args:
        docs: List of documents
        min_length: Minimum word length to consider
        stopwords: Set of words to exclude
    """
    if stopwords is None:
        # Common stopwords to exclude
        stopwords = {
            "that", "this", "with", "from", "have", "been", "were", "would",
            "could", "should", "their", "there", "which", "these", "those",
            "when", "what", "where", "while", "about", "after", "before",
            "between", "into", "through", "during", "also", "such", "very",
            "than", "then", "them", "they", "more", "some", "other", "only",
            "most", "both", "each", "many", "much", "same", "over", "under",
        }
    
    print("⏳ Extracting keywords from documents...")
    keyword_counter = Counter()
    total_docs = len(docs)
    
    for idx, doc in enumerate(docs):
        if (idx + 1) % 500 == 0:
            print(f"   Processed {idx + 1}/{total_docs} documents...")
        
        # Combine title and text
        full_text = f"{doc.title} {doc.text}".lower()
        
        # Extract words (alphanumeric with hyphens)
        words = re.findall(r'\b[a-z][a-z0-9-]*[a-z0-9]\b', full_text)
        
        # Filter and count
        for word in words:
            if (len(word) >= min_length and 
                word not in stopwords and
                not word.isdigit()):
                keyword_counter[word] += 1
    
    print(f"✅ Extracted {len(keyword_counter)} unique keywords\n")
    return keyword_counter


def categorize_keywords(keywords: List[Tuple[str, int]]) -> Dict[str, List[Tuple[str, int]]]:
    """
    Categorize keywords by medical domain using pattern matching
    
    Args:
        keywords: List of (keyword, count) tuples
    
    Returns:
        Dict mapping category -> list of (keyword, count)
    """
    print("⏳ Categorizing keywords by medical domain...")
    
    categorized = defaultdict(list)
    uncategorized = []
    
    for keyword, count in keywords:
        matched = False
        
        # Check each category
        for category, patterns in MEDICAL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, keyword):
                    categorized[category].append((keyword, count))
                    matched = True
                    break
            if matched:
                break
        
        if not matched:
            uncategorized.append((keyword, count))
    
    # Sort each category by count
    for category in categorized:
        categorized[category].sort(key=lambda x: x[1], reverse=True)
    
    print(f"✅ Categorized into {len(categorized)} domains\n")
    print(f"   Uncategorized: {len(uncategorized)} keywords\n")
    
    return dict(categorized), uncategorized


def print_keyword_report(keywords: Counter, top_n: int = 50) -> None:
    """Print top keywords report"""
    print(f"\n{'='*100}")
    print(f"🔍 TOP {top_n} MEDICAL KEYWORDS IN DATASET")
    print(f"{'='*100}\n")
    
    total_count = sum(keywords.values())
    
    print(f"{'Rank':<6} {'Keyword':<30} {'Frequency':<12} {'%':<10}")
    print(f"{'-'*6} {'-'*30} {'-'*12} {'-'*10}")
    
    for rank, (keyword, count) in enumerate(keywords.most_common(top_n), 1):
        percentage = (count / total_count * 100) if total_count > 0 else 0
        print(f"{rank:<6} {keyword:<30} {count:<12,} {percentage:<9.3f}%")


def print_categorized_report(
    categorized: Dict[str, List[Tuple[str, int]]],
    top_per_category: int = 10
) -> None:
    """Print categorized keywords report"""
    print(f"\n{'='*100}")
    print(f"📊 KEYWORDS BY MEDICAL DOMAIN (Top {top_per_category} per domain)")
    print(f"{'='*100}\n")
    
    # Sort categories by total frequency
    category_totals = {
        cat: sum(count for _, count in keywords)
        for cat, keywords in categorized.items()
    }
    sorted_categories = sorted(
        category_totals.items(),
        key=lambda x: x[1],
        reverse=True
    )
    
    for category, total in sorted_categories:
        keywords = categorized[category]
        print(f"\n📌 {category.upper()} (Total: {total:,} occurrences, {len(keywords)} unique terms)")
        print(f"   {'-'*90}")
        print(f"   {'Rank':<6} {'Keyword':<35} {'Frequency':<12} {'% of Domain':<12}")
        print(f"   {'-'*6} {'-'*35} {'-'*12} {'-'*12}")
        
        for rank, (keyword, count) in enumerate(keywords[:top_per_category], 1):
            pct = (count / total * 100) if total > 0 else 0
            print(f"   {rank:<6} {keyword:<35} {count:<12,} {pct:<11.2f}%")


def suggest_competencies(
    categorized: Dict[str, List[Tuple[str, int]]],
    min_threshold: int = 50
) -> List[Dict]:
    """
    Suggest competencies based on keyword frequency
    
    Args:
        categorized: Categorized keywords
        min_threshold: Minimum total occurrences to suggest as competency
    
    Returns:
        List of competency suggestions with evidence
    """
    print(f"\n{'='*100}")
    print(f"💡 SUGGESTED COMPETENCIES (Based on keyword frequency)")
    print(f"{'='*100}\n")
    
    suggestions = []
    
    for category, keywords in categorized.items():
        total = sum(count for _, count in keywords)
        
        if total >= min_threshold:
            top_keywords = [kw for kw, _ in keywords[:5]]
            suggestions.append({
                "competency": category,
                "total_occurrences": total,
                "unique_terms": len(keywords),
                "top_keywords": top_keywords,
                "evidence_strength": "High" if total > 500 else "Medium" if total > 200 else "Low"
            })
    
    # Sort by total occurrences
    suggestions.sort(key=lambda x: x["total_occurrences"], reverse=True)
    
    print(f"{'Competency':<20} {'Occurrences':<15} {'Unique Terms':<15} {'Strength':<12} {'Top Keywords'}")
    print(f"{'-'*20} {'-'*15} {'-'*15} {'-'*12} {'-'*50}")
    
    for sugg in suggestions:
        print(
            f"{sugg['competency']:<20} "
            f"{sugg['total_occurrences']:<15,} "
            f"{sugg['unique_terms']:<15} "
            f"{sugg['evidence_strength']:<12} "
            f"{', '.join(sugg['top_keywords'][:3])}"
        )
    
    return suggestions


def export_results(
    keywords: Counter,
    categorized: Dict[str, List[Tuple[str, int]]],
    suggestions: List[Dict],
    output_prefix: str = "competency_discovery"
) -> None:
    """Export discovery results to CSV and JSON"""
    
    # Export top keywords to CSV
    csv_path = f"{output_prefix}_keywords.csv"
    print(f"\n💾 Exporting keywords to {csv_path}...")
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Keyword", "Frequency", "Percentage"])
        total = sum(keywords.values())
        for rank, (keyword, count) in enumerate(keywords.most_common(200), 1):
            pct = (count / total * 100) if total > 0 else 0
            writer.writerow([rank, keyword, count, f"{pct:.3f}"])
    
    # Export categorized keywords to CSV
    cat_csv_path = f"{output_prefix}_categorized.csv"
    print(f"💾 Exporting categorized keywords to {cat_csv_path}...")
    with open(cat_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Category", "Keyword", "Frequency"])
        for category, kw_list in sorted(categorized.items()):
            for keyword, count in kw_list:
                writer.writerow([category, keyword, count])
    
    # Export suggestions to JSON
    json_path = f"{output_prefix}_suggestions.json"
    print(f"💾 Exporting suggestions to {json_path}...")
    export_data = {
        "suggested_competencies": suggestions,
        "category_summary": {
            cat: {
                "total_occurrences": sum(count for _, count in kw_list),
                "unique_terms": len(kw_list),
                "top_10_keywords": [kw for kw, _ in kw_list[:10]]
            }
            for cat, kw_list in categorized.items()
        },
        "top_100_keywords": [
            {"keyword": kw, "count": count}
            for kw, count in keywords.most_common(100)
        ]
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Export complete!\n")


def main():
    parser = argparse.ArgumentParser(
        description="Discover medical competencies from dataset using keyword analysis"
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=5000,
        help="Maximum documents to analyze (0 for unlimited)"
    )
    parser.add_argument(
        "--top-keywords",
        type=int,
        default=100,
        help="Number of top keywords to analyze"
    )
    parser.add_argument(
        "--min-keyword-length",
        type=int,
        default=4,
        help="Minimum keyword length to consider"
    )
    parser.add_argument(
        "--top-per-category",
        type=int,
        default=10,
        help="Number of top keywords to show per category"
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export results to CSV and JSON files"
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="competency_discovery",
        help="Prefix for output files"
    )
    
    args = parser.parse_args()
    
    # Load documents
    docs = load_documents(args.max_docs)
    
    if not docs:
        print("❌ No documents loaded!")
        return
    
    print(f"📚 Analyzing {len(docs)} documents\n")
    
    # Extract keywords
    keywords = extract_medical_keywords(docs, args.min_keyword_length)
    
    # Print top keywords
    print_keyword_report(keywords, args.top_keywords)
    
    # Categorize keywords
    top_keywords_list = keywords.most_common(args.top_keywords * 2)  # Extra for categorization
    categorized, uncategorized = categorize_keywords(top_keywords_list)
    
    # Print categorized report
    print_categorized_report(categorized, args.top_per_category)
    
    # Suggest competencies
    suggestions = suggest_competencies(categorized)
    
    # Export if requested
    if args.export:
        export_results(keywords, categorized, suggestions, args.output_prefix)
    
    print(f"\n{'='*100}")
    print("✅ Competency discovery complete!")
    print(f"{'='*100}\n")
    
    print("\n💡 Recommendation:")
    print("   Based on the analysis, consider using these competencies for your system:")
    for i, sugg in enumerate(suggestions[:8], 1):  # Top 8 suggestions
        print(f"   {i}. {sugg['competency']} ({sugg['total_occurrences']:,} occurrences)")


if __name__ == "__main__":
    main()
