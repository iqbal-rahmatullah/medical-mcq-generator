from __future__ import annotations

from typing import Dict, List


_COMPETENCY_EXPANSIONS: Dict[str, List[str]] = {
    # ILMU DASAR (Bukti: ~740.000 kemunculan)
    # Mencakup biologi seluler/molekuler, anatomi, dan fisiologi normal
    # Kata kunci teratas: cells (102K), protein (33K), enzyme (25K), blood (32K), tissue (21K)
    # Rasional: Cluster kata kunci terbesar dalam dataset, fondasi pengetahuan medis fundamental
    # Cakupan: mekanisme molekuler, proses seluler, struktur anatomi, sistem tubuh
    "basic_sciences": [
        "cells",
        "cell",
        "protein",
        "enzyme",
        "acid",
        "molecular",
        "synthesis",
        "membrane",
        "binding",
        "gene",
        "anatomy",
        "blood",
        "tissue",
        "muscle",
        "liver",
        "organ",
        "system",
        "physiology",
        "function",
        "normal",
        "activity",
        "homeostasis",
    ],
    
    # PRAKTIK KLINIS (Bukti: ~245.000 kemunculan)
    # Perawatan klinis berpusat pada pasien dan manajemen kasus
    # Kata kunci teratas: patients (88K), patient (20K), clinical (24K), cases (28K)
    # Rasional: Cluster terbesar kedua, mencerminkan aplikasi klinis dari pengetahuan medis
    # Cakupan: perawatan pasien, skenario klinis, studi kasus, pengambilan keputusan klinis
    "clinical_practice": [
        "patients",
        "patient",
        "clinical",
        "cases",
        "case",
        "study",
        "management",
        "care",
        "presentation",
        "history",
        "physical examination",
        "clinical assessment",
        "patient management",
        "clinical scenario",
        "bedside",
        "rounds",
    ],
    
    # PATOLOGI (Bukti: ~155.000 kemunculan)
    # Proses penyakit, kondisi patologis, dan abnormalitas (Deskripsi penyakit dan perubahannya)
    # Kata kunci teratas: disease (45K), infection (20K), tumor (15K), cancer (13K), syndrome (18K)
    # Rasional: Inti dari pemahaman kondisi medis dan manifestasinya
    # Cakupan: penyakit, infeksi, neoplasma, sindrom, proses patologis
    "pathology": [
        "disease",
        "infection",
        "tumor",
        "cancer",
        "syndrome",
        "disorder",
        "pathology",
        "lesion",
        "abnormal",
        "pathological",
        "malignancy",
        "benign",
        "acute",
        "chronic",
        "inflammation",
        "necrosis",
        "fibrosis",
        "metastasis",
    ],
    
    # PENGOBATAN (Bukti: ~113.000 kemunculan)
    # Intervensi terapeutik dan strategi manajemen pasien
    # Kata kunci teratas: treatment (37K), therapy (19K), drugs (12K), drug (12K)
    # Rasional: Kompetensi berorientasi tindakan, sangat relevan untuk praktik klinis
    # Cakupan: obat-obatan, terapi, intervensi bedah, pendekatan manajemen
    "treatment": [
        "treatment",
        "therapy",
        "drug",
        "drugs",
        "medication",
        "pharmacotherapy",
        "surgery",
        "surgical",
        "intervention",
        "management",
        "dose",
        "dosage",
        "administration",
        "prescription",
        "first-line",
        "second-line",
        "guideline",
        "protocol",
        "acute management",
        "long-term management",
    ],
    
    # ETIOLOGI (Bukti: ~72.000 kemunculan)
    # Penyebab, faktor risiko, dan mekanisme penyakit (Penyebab dan mekanisme terjadinya penyakit)
    # Kata kunci teratas: cause (13K), caused (11K), mechanism (8K), associated (25K)
    # Rasional: Memahami "mengapa" penyakit terjadi, esensial untuk pencegahan dan pengobatan
    # Cakupan: kausalitas, faktor risiko, patogenesis, mekanisme penyakit
    "etiology": [
        "cause",
        "caused",
        "causes",
        "etiology",
        "risk",
        "risk factors",
        "mechanism",
        "mechanisms",
        "pathogenesis",
        "associated",
        "predisposing",
        "underlying cause",
        "genetic factors",
        "environmental factors",
        "trigger",
        "precipitating factors",
        "epidemiology",
        "incidence",
        "prevalence",
    ],
    
    # DIAGNOSIS (Bukti: ~60.000 kemunculan)
    # Penilaian klinis, workup diagnostik, dan interpretasi tes
    # Kata kunci teratas: diagnosis (15K), symptoms (12K), test (11K), examination (6K)
    # Rasional: Esensial untuk pengambilan keputusan klinis dan penilaian pasien yang akurat
    # Cakupan: gejala, tanda, tes diagnostik, kriteria klinis, diagnosis banding
    "diagnosis": [
        "diagnosis",
        "diagnostic",
        "symptoms",
        "signs",
        "test",
        "tests",
        "examination",
        "evaluation",
        "assessment",
        "screening",
        "differential diagnosis",
        "clinical features",
        "presentation",
        "findings",
        "laboratory",
        "imaging",
        "workup",
        "diagnostic criteria",
        "sensitivity",
        "specificity",
        "confirmatory test",
    ],
}


def build_query(topic: str, competency: str) -> str:
    topic = topic.strip()
    competency = competency.strip()

    terms: List[str] = []
    if topic:
        terms.append(topic)
    if competency:
        terms.append(competency)

    expansions = _COMPETENCY_EXPANSIONS.get(competency.lower(), [])
    for term in expansions:
        if term not in terms:
            terms.append(term)

    return " ".join(terms)


def build_query_minimal(topic: str, competency: str) -> str:
    topic = topic.strip()
    competency = competency.strip()
    terms = [term for term in (topic, competency) if term]
    return " ".join(terms)


_QUERY_VARIATIONS = [
    ["clinical", "medical", "practice", "patient"],
    ["evidence", "study", "research", "findings"],
    ["diagnosis", "treatment", "management", "therapy"],
    ["pathophysiology", "mechanism", "cause", "etiology"],
    ["symptoms", "signs", "presentation", "manifestation"],
]


def build_query_varied(topic: str, competency: str, variation_index: int = 0) -> str:
    base_query = build_query(topic, competency)
    
    idx = variation_index % len(_QUERY_VARIATIONS)
    variation_terms = _QUERY_VARIATIONS[idx]
    
    base_lower = base_query.lower()
    new_terms = [t for t in variation_terms if t.lower() not in base_lower]
    
    if not new_terms:
        return base_query
    
    selected = new_terms[:2]
    return f"{base_query} {' '.join(selected)}"

