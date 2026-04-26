from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.corpus.loaders import load_pubmed_hf, load_textbooks_hf
from app.corpus.models import Document
from app.core.config import settings


def load_documents(
    source: str = "both", 
    max_docs: int = 0
) -> List[Document]:
    """
    Load documents from specified source
    
    Args:
        source: "pubmed", "textbooks", or "both"
        max_docs: Maximum documents to load (0 = unlimited)
    """
    docs = []
    
    if source in ("pubmed", "both"):
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
    
    if source in ("textbooks", "both"):
        print(f"📥 Loading Textbooks documents...")
        start_idx = len(docs)
        textbook_limit = max_docs if max_docs > 0 else settings.CORPUS_TEXTBOOKS_MAX_DOCS
        for i, doc in enumerate(load_textbooks_hf(
            settings.CORPUS_TEXTBOOKS_HF_DATASET,
            local_files_only=settings.CORPUS_HF_LOCAL_ONLY,
            streaming=settings.CORPUS_HF_STREAMING,
        )):
            docs.append(doc)
            if textbook_limit and i + 1 >= textbook_limit:
                break
        print(f"✅ Loaded {len(docs) - start_idx} Textbooks documents")
    
    return docs


def preview_documents(docs: List[Document], n: int = 10) -> None:
    """Show top N documents"""
    print(f"\n{'='*80}")
    print(f"📄 TOP {n} DOCUMENTS")
    print(f"{'='*80}\n")
    
    for i, doc in enumerate(docs[:n], 1):
        print(f"[{i}] Doc ID: {doc.doc_id}")
        print(f"    Source: {doc.source}")
        print(f"    Title: {doc.title[:100]}{'...' if len(doc.title) > 100 else ''}")
        print(f"    Text Length: {len(doc.text)} chars")
        print(f"    Preview: {doc.text[:200]}{'...' if len(doc.text) > 200 else ''}")
        print()


def analyze_statistics(docs: List[Document]) -> None:
    """Calculate and display dataset statistics"""
    print(f"\n{'='*80}")
    print(f"📊 DATASET STATISTICS")
    print(f"{'='*80}\n")
    
    # Source distribution
    source_counts = Counter(doc.source for doc in docs)
    print(f"📚 Total Documents: {len(docs)}")
    for source, count in source_counts.items():
        print(f"   └─ {source}: {count} ({count/len(docs)*100:.1f}%)")
    
    # Text length statistics
    text_lengths = [len(doc.text) for doc in docs]
    avg_length = sum(text_lengths) / len(text_lengths) if text_lengths else 0
    min_length = min(text_lengths) if text_lengths else 0
    max_length = max(text_lengths) if text_lengths else 0
    
    print(f"\n📏 Text Length (chars):")
    print(f"   ├─ Average: {avg_length:.0f}")
    print(f"   ├─ Minimum: {min_length}")
    print(f"   └─ Maximum: {max_length}")
    
    # Title length statistics
    title_lengths = [len(doc.title) for doc in docs]
    avg_title_length = sum(title_lengths) / len(title_lengths) if title_lengths else 0
    
    print(f"\n📝 Title Length (chars):")
    print(f"   └─ Average: {avg_title_length:.0f}")


def analyze_keywords(docs: List[Document], top_n: int = 20) -> None:
    """Find most common keywords/terms in the dataset"""
    print(f"\n{'='*80}")
    print(f"🔍 TOP {top_n} KEYWORDS/TERMS")
    print(f"{'='*80}\n")
    
    # Extract words (simple tokenization)
    word_counter = Counter()
    
    print("⏳ Tokenizing documents...")
    for doc in docs:
        # Combine title and text
        full_text = f"{doc.title} {doc.text}".lower()
        # Simple word extraction (alphanumeric only)
        words = [
            word for word in full_text.split() 
            if len(word) > 3 and word.isalnum()  # Filter short words
        ]
        word_counter.update(words)
    
    print(f"✅ Found {len(word_counter)} unique terms\n")
    
    # Display top N
    print(f"{'Rank':<6} {'Term':<25} {'Frequency':<12} {'%':<8}")
    print(f"{'-'*6} {'-'*25} {'-'*12} {'-'*8}")
    
    total_words = sum(word_counter.values())
    for rank, (term, count) in enumerate(word_counter.most_common(top_n), 1):
        percentage = (count / total_words * 100) if total_words > 0 else 0
        print(f"{rank:<6} {term:<25} {count:<12,} {percentage:<8.3f}")


def analyze_medical_terms(docs: List[Document], top_n: int = 20) -> None:
    """Find common medical terms (words with medical suffixes/prefixes)"""
    print(f"\n{'='*80}")
    print(f"🏥 TOP {top_n} MEDICAL TERMS")
    print(f"{'='*80}\n")
    
    # Medical indicators
    medical_patterns = [
        'itis', 'osis', 'ectomy', 'oma', 'emia', 'pathy', 'plasty',
        'scopy', 'therapy', 'ology', 'gram', 'cardio', 'neuro', 'hepat',
        'gastr', 'pulmon', 'renal', 'thyroid', 'diabet', 'cancer',
        'disease', 'syndrome', 'treatment', 'patient', 'clinical'
    ]
    
    medical_words = Counter()
    
    print("⏳ Extracting medical terms...")
    for doc in docs:
        full_text = f"{doc.title} {doc.text}".lower()
        words = [word for word in full_text.split() if len(word) > 3 and word.isalnum()]
        
        # Filter medical terms
        for word in words:
            if any(pattern in word for pattern in medical_patterns):
                medical_words[word] += 1
    
    print(f"✅ Found {len(medical_words)} medical terms\n")
    
    print(f"{'Rank':<6} {'Term':<30} {'Frequency':<12}")
    print(f"{'-'*6} {'-'*30} {'-'*12}")
    
    for rank, (term, count) in enumerate(medical_words.most_common(top_n), 1):
        print(f"{rank:<6} {term:<30} {count:<12,}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze medical corpus dataset"
    )
    parser.add_argument(
        "--source",
        choices=["pubmed", "textbooks", "both"],
        default="both",
        help="Which dataset to analyze"
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=1000,
        help="Maximum documents to load (0 for unlimited)"
    )
    parser.add_argument(
        "--preview",
        type=int,
        default=10,
        help="Number of documents to preview"
    )
    parser.add_argument(
        "--top-keywords",
        type=int,
        default=20,
        help="Number of top keywords to show"
    )
    parser.add_argument(
        "--skip-preview",
        action="store_true",
        help="Skip document preview"
    )
    parser.add_argument(
        "--skip-keywords",
        action="store_true",
        help="Skip keyword analysis"
    )
    parser.add_argument(
        "--skip-medical",
        action="store_true",
        help="Skip medical terms analysis"
    )
    
    args = parser.parse_args()
    
    # Load documents
    docs = load_documents(args.source, args.max_docs)
    
    if not docs:
        print("❌ No documents loaded!")
        return
    
    # Run analyses
    if not args.skip_preview:
        preview_documents(docs, args.preview)
    
    analyze_statistics(docs)
    
    if not args.skip_keywords:
        analyze_keywords(docs, args.top_keywords)
    
    if not args.skip_medical:
        analyze_medical_terms(docs, args.top_keywords)
    
    print(f"\n{'='*80}")
    print("✅ Analysis complete!")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
