#!/usr/bin/env python3
"""
Medical Competency Analysis Tool

Extract medical competencies from dataset and validate against
existing competency definitions for research evidence.

Usage:
    python app/scripts/analyze_competencies.py --max-docs 5000
    python app/scripts/analyze_competencies.py --export-csv results.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.models import Document
from app.core.config import settings

# Import existing competency expansions
from app.retrieval.query_builder import _COMPETENCY_EXPANSIONS


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


def extract_competency_terms(docs: List[Document]) -> Dict[str, Counter]:
    """
    Extract frequency of competency-related terms from documents
    
    Returns:
        Dict mapping competency -> Counter of expansion terms
    """
    print("⏳ Extracting competency terms from documents...")
    
    competency_counters = {
        competency: Counter() for competency in _COMPETENCY_EXPANSIONS
    }
    
    total_docs = len(docs)
    for idx, doc in enumerate(docs):
        if (idx + 1) % 500 == 0:
            print(f"   Processed {idx + 1}/{total_docs} documents...")
        
        # Combine title and text, lowercase for matching
        full_text = f"{doc.title} {doc.text}".lower()
        
        # Count occurrences of each expansion term
        for competency, expansions in _COMPETENCY_EXPANSIONS.items():
            for term in expansions:
                # Count whole word occurrences
                term_lower = term.lower()
                count = full_text.count(term_lower)
                if count > 0:
                    competency_counters[competency][term] += count
    
    print(f"✅ Extraction complete!\n")
    return competency_counters


def analyze_competency_coverage(
    competency_counters: Dict[str, Counter]
) -> Dict[str, Dict]:
    """
    Analyze coverage of each competency in the dataset
    
    Returns:
        Statistics for each competency
    """
    coverage = {}
    
    for competency, counter in competency_counters.items():
        total_occurrences = sum(counter.values())
        unique_terms_found = len([term for term, count in counter.items() if count > 0])
        total_terms_defined = len(_COMPETENCY_EXPANSIONS[competency])
        
        coverage[competency] = {
            "total_occurrences": total_occurrences,
            "unique_terms_found": unique_terms_found,
            "total_terms_defined": total_terms_defined,
            "coverage_ratio": unique_terms_found / total_terms_defined if total_terms_defined > 0 else 0,
            "top_terms": counter.most_common(5),
        }
    
    return coverage


def print_coverage_report(coverage: Dict[str, Dict]) -> None:
    """Print competency coverage report"""
    print(f"\n{'='*100}")
    print(f"📊 COMPETENCY COVERAGE ANALYSIS")
    print(f"{'='*100}\n")
    
    # Sort by total occurrences
    sorted_competencies = sorted(
        coverage.items(),
        key=lambda x: x[1]["total_occurrences"],
        reverse=True
    )
    
    print(f"{'Competency':<20} {'Occurrences':<15} {'Terms Found':<15} {'Coverage':<12} {'Top Term':<30}")
    print(f"{'-'*20} {'-'*15} {'-'*15} {'-'*12} {'-'*30}")
    
    for competency, stats in sorted_competencies:
        coverage_pct = stats["coverage_ratio"] * 100
        top_term = stats["top_terms"][0] if stats["top_terms"] else ("N/A", 0)
        
        print(
            f"{competency:<20} "
            f"{stats['total_occurrences']:<15,} "
            f"{stats['unique_terms_found']}/{stats['total_terms_defined']:<13} "
            f"{coverage_pct:<11.1f}% "
            f"{top_term[0]} ({top_term[1]:,})"
        )


def print_detailed_analysis(
    competency_counters: Dict[str, Counter],
    top_n: int = 10
) -> None:
    """Print detailed analysis for each competency"""
    print(f"\n{'='*100}")
    print(f"🔍 DETAILED COMPETENCY ANALYSIS (Top {top_n} terms per competency)")
    print(f"{'='*100}\n")
    
    for competency in sorted(_COMPETENCY_EXPANSIONS.keys()):
        counter = competency_counters[competency]
        total = sum(counter.values())
        
        print(f"\n📌 {competency.upper()} (Total: {total:,} occurrences)")
        print(f"   {'-'*90}")
        
        if not counter:
            print("   ⚠️  No occurrences found in dataset")
            continue
        
        print(f"   {'Rank':<6} {'Term':<30} {'Count':<12} {'% of Competency':<15}")
        print(f"   {'-'*6} {'-'*30} {'-'*12} {'-'*15}")
        
        for rank, (term, count) in enumerate(counter.most_common(top_n), 1):
            pct = (count / total * 100) if total > 0 else 0
            print(f"   {rank:<6} {term:<30} {count:<12,} {pct:<14.2f}%")


def export_to_csv(
    competency_counters: Dict[str, Counter],
    coverage: Dict[str, Dict],
    output_path: str
) -> None:
    """Export analysis results to CSV for research"""
    print(f"\n💾 Exporting results to {output_path}...")
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write summary table
        writer.writerow([])
        writer.writerow(["COMPETENCY COVERAGE SUMMARY"])
        writer.writerow([
            "Competency",
            "Total Occurrences",
            "Unique Terms Found",
            "Total Terms Defined",
            "Coverage %",
            "Top Term",
            "Top Term Count"
        ])
        
        for competency, stats in sorted(
            coverage.items(),
            key=lambda x: x[1]["total_occurrences"],
            reverse=True
        ):
            top_term = stats["top_terms"][0] if stats["top_terms"] else ("N/A", 0)
            writer.writerow([
                competency,
                stats["total_occurrences"],
                stats["unique_terms_found"],
                stats["total_terms_defined"],
                f"{stats['coverage_ratio'] * 100:.1f}",
                top_term[0],
                top_term[1]
            ])
        
        # Write detailed term frequencies
        writer.writerow([])
        writer.writerow(["DETAILED TERM FREQUENCIES"])
        writer.writerow(["Competency", "Term", "Frequency"])
        
        for competency in sorted(_COMPETENCY_EXPANSIONS.keys()):
            counter = competency_counters[competency]
            for term, count in counter.most_common():
                writer.writerow([competency, term, count])
    
    print(f"✅ Export complete!")


def export_to_json(
    competency_counters: Dict[str, Counter],
    coverage: Dict[str, Dict],
    output_path: str
) -> None:
    """Export analysis results to JSON"""
    print(f"\n💾 Exporting results to {output_path}...")
    
    # Convert Counter objects to dicts for JSON serialization
    export_data = {
        "coverage_summary": coverage,
        "term_frequencies": {
            competency: dict(counter.most_common())
            for competency, counter in competency_counters.items()
        },
        "competency_definitions": _COMPETENCY_EXPANSIONS
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Export complete!")


def generate_latex_table(coverage: Dict[str, Dict]) -> str:
    """Generate LaTeX table for research paper"""
    lines = [
        "\\begin{table}[ht]",
        "\\centering",
        "\\caption{Medical Competency Coverage in Dataset}",
        "\\label{tab:competency_coverage}",
        "\\begin{tabular}{lrrrc}",
        "\\hline",
        "\\textbf{Competency} & \\textbf{Occurrences} & \\textbf{Terms} & \\textbf{Coverage} & \\textbf{Top Term} \\\\",
        "\\hline",
    ]
    
    for competency, stats in sorted(
        coverage.items(),
        key=lambda x: x[1]["total_occurrences"],
        reverse=True
    ):
        top_term = stats["top_terms"][0] if stats["top_terms"] else ("N/A", 0)
        lines.append(
            f"{competency} & "
            f"{stats['total_occurrences']:,} & "
            f"{stats['unique_terms_found']}/{stats['total_terms_defined']} & "
            f"{stats['coverage_ratio'] * 100:.1f}\\% & "
            f"{top_term[0]} ({top_term[1]:,}) \\\\"
        )
    
    lines.extend([
        "\\hline",
        "\\end{tabular}",
        "\\end{table}"
    ])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze medical competencies in corpus dataset"
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=5000,
        help="Maximum documents to analyze (0 for unlimited)"
    )
    parser.add_argument(
        "--top-terms",
        type=int,
        default=10,
        help="Number of top terms to show per competency"
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        help="Export results to CSV file"
    )
    parser.add_argument(
        "--export-json",
        type=str,
        help="Export results to JSON file"
    )
    parser.add_argument(
        "--export-latex",
        type=str,
        help="Export LaTeX table to file"
    )
    parser.add_argument(
        "--skip-detailed",
        action="store_true",
        help="Skip detailed per-competency analysis"
    )
    
    args = parser.parse_args()
    
    # Load documents
    docs = load_documents(args.max_docs)
    
    if not docs:
        print("❌ No documents loaded!")
        return
    
    print(f"📚 Analyzing {len(docs)} documents for {len(_COMPETENCY_EXPANSIONS)} competencies\n")
    
    # Extract competency terms
    competency_counters = extract_competency_terms(docs)
    
    # Analyze coverage
    coverage = analyze_competency_coverage(competency_counters)
    
    # Print reports
    print_coverage_report(coverage)
    
    if not args.skip_detailed:
        print_detailed_analysis(competency_counters, args.top_terms)
    
    # Export if requested
    if args.export_csv:
        export_to_csv(competency_counters, coverage, args.export_csv)
    
    if args.export_json:
        export_to_json(competency_counters, coverage, args.export_json)
    
    if args.export_latex:
        latex_table = generate_latex_table(coverage)
        with open(args.export_latex, 'w') as f:
            f.write(latex_table)
        print(f"\n💾 LaTeX table exported to {args.export_latex}")
    
    print(f"\n{'='*100}")
    print("✅ Competency analysis complete!")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()
