from __future__ import annotations

import argparse
import random
import time
from typing import List

from app.core.config import settings
from app.logging.question_bank import load_question_bank
from app.schemas.request import GenerateRequestItem
from app.services import pipeline


TOPICS = [
    "Hypertension",
    "Diabetes mellitus",
    "Asthma",
    "Chronic obstructive pulmonary disease",
    "Pneumonia",
    "Tuberculosis",
    "Anemia",
    "Iron deficiency anemia",
    "Heart failure",
    "Myocardial infarction",
    "Stroke",
    "Epilepsy",
    "Migraine",
    "Depression",
    "Anxiety disorder",
    "Schizophrenia",
    "Obesity",
    "Malnutrition",
    "Chronic kidney disease",
    "Acute kidney injury",
    "Urinary tract infection",
    "Sepsis",
    "Hepatitis B",
    "Hepatitis C",
    "Cirrhosis",
    "Peptic ulcer disease",
    "GERD",
    "Pancreatitis",
    "Appendicitis",
    "Osteoporosis",
    "Rheumatoid arthritis",
    "Osteoarthritis",
    "Systemic lupus erythematosus",
    "Hyperthyroidism",
    "Hypothyroidism",
    "Pregnancy",
    "Preeclampsia",
    "Postpartum hemorrhage",
    "Neonatal sepsis",
    "Immunization",
    "HIV",
    "Influenza",
    "COVID-19",
    "Malaria",
    "Dengue",
    "Typhoid fever",
    "Diarrhea",
    "Dehydration",
    "Smoking cessation",
    "Hyperlipidemia",
    "Atrial fibrillation",
    "Deep vein thrombosis",
    "Pulmonary embolism",
    "Breast cancer",
    "Cervical cancer",
    "Prostate cancer",
    "Colorectal cancer",
    "Chronic pain",
    "Back pain",
    "Dermatitis",
    "Acne",
    "Psoriasis",
    "Allergic rhinitis",
]

COMPETENCIES = [
    "Diagnosis",
    "Treatment",
    "Therapy",
    "Etiology",
    "Prevention",
    "Prognosis",
    "Screening",
    "Complications",
    "Pathophysiology",
    "Pharmacology",
    "Monitoring",
    "Investigation",
]


def _count_bank_items() -> int:
    return len(load_question_bank(settings.QUESTION_BANK_PATH))


def _build_payload(batch_size: int, n_questions: int) -> List[GenerateRequestItem]:
    payload: List[GenerateRequestItem] = []
    for _ in range(batch_size):
        topic = random.choice(TOPICS)
        competency = random.choice(COMPETENCIES)
        payload.append(
            GenerateRequestItem(
                topic=topic,
                competency=competency,
                n_questions=n_questions,
            )
        )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=1000, help="Target OK questions.")
    parser.add_argument("--batch-size", type=int, default=10, help="Items per batch.")
    parser.add_argument("--n-questions", type=int, default=1, help="Questions per item.")
    parser.add_argument("--max-rounds", type=int, default=500, help="Safety stop.")
    parser.add_argument("--sleep-sec", type=float, default=0.0, help="Sleep between batches.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed (0 = random).")
    args = parser.parse_args()

    if args.seed:
        random.seed(args.seed)

    start_count = _count_bank_items()
    target = max(args.target, start_count)
    print(f"Question bank path: {settings.QUESTION_BANK_PATH}")
    print(f"Starting OK count: {start_count}, target: {target}")

    rounds = 0
    while _count_bank_items() < target and rounds < args.max_rounds:
        rounds += 1
        payload = _build_payload(args.batch_size, args.n_questions)
        pipeline.run_pipeline_batch(payload)
        current = _count_bank_items()
        print(f"[{rounds}] OK count: {current}")
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    final_count = _count_bank_items()
    print(f"Final OK count: {final_count}")
    if final_count < target:
        print("Stopped before reaching target. Consider increasing --max-rounds.")


if __name__ == "__main__":
    main()
