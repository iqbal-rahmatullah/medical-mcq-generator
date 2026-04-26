"""
Export Top 20 Questions to PDF for Expert Review

Menggunakan logic evaluasi yang sama dengan app/eval/
Ranking berdasarkan: composite_score = 0.4*rougeL + 0.3*semantic + 0.3*nli
"""

import json
import sys
import os
import logging
from pathlib import Path

# Setup path agar bisa import app modules
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
LOGGER = logging.getLogger(__name__)

JSONL_PATH = "app/logging/question_bank.jsonl"
OUTPUT_PDF = "docs/expert_review_top20.pdf"


# ─── Step 1: ROUGE scoring (no GPU needed) ──────────────────────────────────
def run_rouge():
    LOGGER.info("Menghitung ROUGE scores...")
    from app.eval.rouge_eval import evaluate_question_bank
    result = evaluate_question_bank(JSONL_PATH, limit=0, include_items=True)
    LOGGER.info(f"ROUGE selesai: {result.scored} soal dinilai")
    return {item["stem"]: item for item in (result.items or [])}


# ─── Step 2: Semantic + NLI scoring ─────────────────────────────────────────
def run_semantic_nli(rouge_map):
    from app.core.config import settings
    from app.eval.semantic_eval import evaluate_question_bank_semantic
    from app.eval.nli_eval import evaluate_question_bank_nli

    LOGGER.info("Menghitung Semantic Similarity (BiomedNLP-PubMedBERT)...")
    sem_result = evaluate_question_bank_semantic(
        JSONL_PATH,
        model_name=settings.SEMANTIC_MODEL,
        limit=0,
        include_items=True,
    )
    LOGGER.info(f"Semantic selesai: avg={sem_result.avg_cosine:.4f}")
    sem_map = {item["stem"]: item for item in (sem_result.items or [])}

    LOGGER.info("Menghitung NLI Entailment (PubMedBERT-MNLI)...")
    nli_result = evaluate_question_bank_nli(
        JSONL_PATH,
        model_name=settings.NLI_MODEL,
        limit=0,
        include_items=True,
    )
    LOGGER.info(f"NLI selesai: avg entailment={nli_result.avg_entailment:.4f}")
    nli_map = {item["stem"]: item for item in (nli_result.items or [])}

    return sem_map, nli_map


# ─── Step 3: Merge & Rank ────────────────────────────────────────────────────
def merge_and_rank(rouge_map, sem_map, nli_map):
    LOGGER.info("Menggabungkan skor & memilih Top 20...")

    # Load original questions untuk mendapatkan semua field
    questions = {}
    with open(JSONL_PATH) as f:
        for line in f:
            if line.strip():
                q = json.loads(line)
                if q.get("status") == "OK":
                    questions[q["stem"]] = q

    ranked = []
    for stem, q in questions.items():
        rouge_item = rouge_map.get(stem, {})
        sem_item = sem_map.get(stem, {})
        nli_item = nli_map.get(stem, {})

        rougeL = rouge_item.get("rougeL_f1", 0.0)
        rouge1 = rouge_item.get("rouge1_f1", 0.0)
        semantic = sem_item.get("cosine_similarity", 0.0)
        nli_ent = nli_item.get("entailment", 0.0)

        # Skip jika tidak ada skor sama sekali
        if rougeL == 0.0 and semantic == 0.0 and nli_ent == 0.0:
            continue

        composite = 0.4 * rougeL + 0.3 * semantic + 0.3 * nli_ent

        ranked.append({
            "no": 0,
            "topic": q.get("topic", ""),
            "competency": q.get("competency", ""),
            "stem": stem,
            "options": q.get("options", {}),
            "answer_key": q.get("answer_key", ""),
            "explanation": q.get("explanation", ""),
            "rouge1_f1": rouge1,
            "rougeL_f1": rougeL,
            "semantic": semantic,
            "nli_entailment": nli_ent,
            "composite_score": composite,
        })

    ranked.sort(key=lambda x: x["composite_score"], reverse=True)
    top20 = ranked[:20]
    for i, item in enumerate(top20, start=1):
        item["no"] = i

    LOGGER.info(f"Top 20 dipilih dari {len(ranked)} soal valid")
    return top20


# ─── Step 4: Export PDF ──────────────────────────────────────────────────────
def export_pdf(top20):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

    os.makedirs("docs", exist_ok=True)
    doc = SimpleDocTemplate(
        OUTPUT_PDF,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()

    style_title = ParagraphStyle("title", parent=styles["Title"],
        fontSize=16, spaceAfter=6, alignment=TA_CENTER,
        textColor=colors.HexColor("#1a1a2e"))
    style_subtitle = ParagraphStyle("subtitle", parent=styles["Normal"],
        fontSize=10, spaceAfter=4, alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"))
    style_h1 = ParagraphStyle("h1", parent=styles["Heading1"],
        fontSize=12, spaceBefore=10, spaceAfter=4,
        textColor=colors.HexColor("#16213e"),
        backColor=colors.HexColor("#e8f4f8"),
        leftIndent=-5, borderPad=4)
    style_label = ParagraphStyle("label", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#888888"),
        spaceAfter=1, fontName="Helvetica-Bold")
    style_body = ParagraphStyle("body", parent=styles["Normal"],
        fontSize=10, spaceAfter=4, leading=14, alignment=TA_JUSTIFY)
    style_option = ParagraphStyle("option", parent=styles["Normal"],
        fontSize=10, spaceAfter=2, leftIndent=10, leading=13)
    style_answer = ParagraphStyle("answer", parent=styles["Normal"],
        fontSize=10, spaceAfter=2, textColor=colors.HexColor("#1b5e20"),
        fontName="Helvetica-Bold")
    style_expl = ParagraphStyle("expl", parent=styles["Normal"],
        fontSize=9, spaceAfter=4, leading=12, textColor=colors.HexColor("#444444"),
        alignment=TA_JUSTIFY, leftIndent=5)
    style_score_label = ParagraphStyle("score_label", parent=styles["Normal"],
        fontSize=8, textColor=colors.HexColor("#666666"), fontName="Helvetica")

    story = []

    # ── Questions ──
    for q in top20:
        opts = q.get("options", {})
        answer_key = q.get("answer_key", "")
        correct_text = opts.get(answer_key, "")

        # Question header
        story.append(Paragraph(
            f'<b>Soal {q["no"]}</b> &nbsp;|&nbsp; '
            f'<font color="#1565C0">{q["topic"]}</font> — {q["competency"]}',
            style_h1
        ))

        # Stem
        story.append(Paragraph("<b>Stem (Kasus Klinis):</b>", style_label))
        story.append(Paragraph(q["stem"], style_body))
        story.append(Spacer(1, 0.2*cm))

        # Options
        story.append(Paragraph("<b>Pilihan Jawaban:</b>", style_label))
        for key in ["A", "B", "C", "D", "E"]:
            text = opts.get(key, "")
            if not text:
                continue
            if key == answer_key:
                story.append(Paragraph(f'<b>{key}. {text}</b> ✓', style_answer))
            else:
                story.append(Paragraph(f'{key}. {text}', style_option))

        story.append(Spacer(1, 0.2*cm))

        # Explanation
        if q.get("explanation"):
            story.append(Paragraph("<b>Penjelasan Kunci Jawaban:</b>", style_label))
            story.append(Paragraph(q["explanation"], style_expl))

        story.append(Spacer(1, 0.6*cm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
        story.append(Spacer(1, 0.3*cm))

        # Page break every 2 questions to keep readable
        if q["no"] % 3 == 0 and q["no"] < 20:
            story.append(PageBreak())

    doc.build(story)
    LOGGER.info(f"PDF berhasil dibuat: {OUTPUT_PDF}")
    print(f"\n✅ PDF expert review: {OUTPUT_PDF}")


# ─── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    LOGGER.info("=== Export Top 20 Questions untuk Expert Review ===")

    # Score
    rouge_map = run_rouge()

    sem_map, nli_map = run_semantic_nli(rouge_map)

    # Rank & pick top 20
    top20 = merge_and_rank(rouge_map, sem_map, nli_map)

    # Print preview
    print(f"\n{'No':<4} {'Topic':<20} {'Competency':<20} {'ROUGE-L':>8} {'Semantic':>9} {'NLI':>7} {'Score':>7}")
    print("-" * 80)
    for q in top20:
        print(f"{q['no']:<4} {q['topic'][:18]:<20} {q['competency'][:18]:<20} "
              f"{q['rougeL_f1']:>8.4f} {q['semantic']:>9.4f} {q['nli_entailment']:>7.4f} {q['composite_score']:>7.4f}")

    # Export PDF
    export_pdf(top20)
