from __future__ import annotations

from typing import Optional

# Few-shot examples
FEW_SHOT_EXAMPLES = {
    "basic_sciences": """
EXAMPLE MCQ (Basic Sciences):
{
  "topic": "Enzyme Kinetics",
  "competency": "basic_sciences",
  "stem": "A researcher is studying an enzyme that follows Michaelis-Menten kinetics. When the substrate concentration equals the Km value, what percentage of the enzyme's maximum velocity (Vmax) is achieved?",
  "options": {
    "A": "25%",
    "B": "50%",
    "C": "75%",
    "D": "100%"
  },
  "answer_key": "B",
  "explanation": "When [S] = Km, the Michaelis-Menten equation simplifies to V = Vmax/2. This is because at [S] = Km, the enzyme is operating at half of its maximum velocity, which represents 50% of Vmax.",
  "evidence": [{"source": "textbook", "doc_id": "enzyme_001", "title": "Biochemistry", "span_text": "The Michaelis constant Km is defined as the substrate concentration at which the reaction velocity is half of Vmax."}],
  "status": "OK"
}
""",
    "clinical_practice": """
EXAMPLE MCQ (Clinical Practice):
{
  "topic": "Diabetes Management",
  "competency": "clinical_practice",
  "stem": "A 58-year-old woman with type 2 diabetes mellitus presents for routine follow-up. Her HbA1c is 8.2% despite maximum dose metformin. She has a BMI of 32 kg/m2 and mild chronic kidney disease (eGFR 55 mL/min). Which medication should be added next?",
  "options": {
    "A": "Glipizide",
    "B": "Empagliflozin",
    "C": "Pioglitazone",
    "D": "Insulin glargine"
  },
  "answer_key": "B",
  "explanation": "SGLT2 inhibitors like empagliflozin are recommended as second-line therapy for patients with type 2 diabetes and CKD due to their dual benefits of glycemic control and renal protection. They also promote weight loss, which benefits this patient with obesity.",
  "evidence": [{"source": "guideline", "doc_id": "ada_2024", "title": "ADA Standards of Care", "span_text": "In patients with T2DM and CKD with eGFR ≥20 mL/min, an SGLT2 inhibitor is recommended to reduce CKD progression and cardiovascular events."}],
  "status": "OK"
}
""",
    "pathology": """
EXAMPLE MCQ (Pathology):
{
  "topic": "Lung Cancer",
  "competency": "pathology",
  "stem": "A 65-year-old male smoker presents with hemoptysis and weight loss. Chest CT shows a central lung mass with hilar lymphadenopathy. Biopsy reveals malignant cells with neuroendocrine differentiation and high mitotic rate. Which type of lung cancer is most likely?",
  "options": {
    "A": "Adenocarcinoma",
    "B": "Squamous cell carcinoma",
    "C": "Small cell lung carcinoma",
    "D": "Large cell carcinoma"
  },
  "answer_key": "C",
  "explanation": "Small cell lung carcinoma (SCLC) is characterized by neuroendocrine differentiation, high mitotic rate, central location, and strong association with smoking. It typically presents with hilar masses and early metastasis.",
  "evidence": [{"source": "textbook", "doc_id": "robbins_path", "title": "Robbins Pathology", "span_text": "Small cell carcinoma shows neuroendocrine differentiation with expression of chromogranin and synaptophysin, extremely high mitotic rate, and typically presents as central hilar masses."}],
  "status": "OK"
}
""",
    "treatment": """
EXAMPLE MCQ (Treatment):
{
  "topic": "Antibiotic Therapy",
  "competency": "treatment",
  "stem": "A 45-year-old man is diagnosed with community-acquired pneumonia requiring hospitalization. He has no drug allergies and normal renal function. His CURB-65 score is 2. Which antibiotic regimen is most appropriate?",
  "options": {
    "A": "Amoxicillin alone",
    "B": "Azithromycin alone",
    "C": "Ceftriaxone plus azithromycin",
    "D": "Vancomycin plus piperacillin-tazobactam"
  },
  "answer_key": "C",
  "explanation": "For hospitalized patients with CAP and CURB-65 score of 2, guidelines recommend a beta-lactam (ceftriaxone) plus a macrolide (azithromycin) or respiratory fluoroquinolone monotherapy to cover typical and atypical pathogens.",
  "evidence": [{"source": "guideline", "doc_id": "ats_cap", "title": "ATS/IDSA CAP Guidelines", "span_text": "For non-severe CAP in hospitalized patients, recommended empiric therapy is a beta-lactam plus macrolide or respiratory fluoroquinolone monotherapy."}],
  "status": "OK"
}
""",
    "etiology": """
EXAMPLE MCQ (Etiology):
{
  "topic": "Peptic Ulcer Disease",
  "competency": "etiology",
  "stem": "A 48-year-old man presents with epigastric pain that improves with eating. Upper endoscopy reveals a duodenal ulcer. Which of the following is the most common etiology of duodenal ulcers?",
  "options": {
    "A": "Zollinger-Ellison syndrome",
    "B": "Helicobacter pylori infection",
    "C": "NSAID use",
    "D": "Crohn's disease"
  },
  "answer_key": "B",
  "explanation": "Helicobacter pylori infection is the most common cause of duodenal ulcers, accounting for approximately 70-90% of cases. The bacteria disrupts the protective mucosal barrier and stimulates gastric acid secretion.",
  "evidence": [{"source": "pubmed", "doc_id": "peptic_001", "title": "Etiology of Peptic Ulcer", "span_text": "Helicobacter pylori infection remains the predominant cause of peptic ulcer disease, responsible for approximately 70-90% of duodenal ulcers and 60-70% of gastric ulcers worldwide."}],
  "status": "OK"
}
""",
    "diagnosis": """
EXAMPLE MCQ (Diagnosis):
{
  "topic": "Acute Appendicitis",
  "competency": "diagnosis",
  "stem": "A 22-year-old woman presents with 12 hours of periumbilical pain that has migrated to the right lower quadrant. She has fever, anorexia, and rebound tenderness at McBurney's point. Which finding would most strongly support the diagnosis of acute appendicitis?",
  "options": {
    "A": "WBC count of 8,000/μL",
    "B": "Positive psoas sign",
    "C": "Normal abdominal CT scan",
    "D": "Decreased bowel sounds"
  },
  "answer_key": "B",
  "explanation": "A positive psoas sign (pain with hip extension) indicates retroperitoneal inflammation, strongly suggesting an inflamed retrocecal appendix. Combined with the classic migration of pain and McBurney's point tenderness, this supports acute appendicitis.",
  "evidence": [{"source": "textbook", "doc_id": "surg_001", "title": "Principles of Surgery", "span_text": "The psoas sign is elicited by passive extension of the right hip, which stretches the iliopsoas muscle and causes pain when an inflamed appendix lies in the retrocecal position."}],
  "status": "OK"
}
""",
}

# Fallback example
DEFAULT_EXAMPLE = """
EXAMPLE MCQ:
{
  "topic": "General Medicine",
  "competency": "clinical_practice",
  "stem": "A 50-year-old patient presents with fatigue and pallor. Laboratory studies show hemoglobin of 8.5 g/dL and MCV of 68 fL. Which initial test is most appropriate?",
  "options": {
    "A": "Vitamin B12 level",
    "B": "Serum ferritin",
    "C": "Hemoglobin electrophoresis",
    "D": "Bone marrow biopsy"
  },
  "answer_key": "B",
  "explanation": "Microcytic anemia (low MCV) with fatigue suggests iron deficiency anemia as the most common cause. Serum ferritin is the most sensitive initial test for iron stores.",
  "evidence": [{"source": "textbook", "doc_id": "heme_001", "title": "Hematology", "span_text": "Serum ferritin is the most sensitive marker for iron deficiency, with levels below 30 ng/mL being diagnostic."}],
  "status": "OK"
}
"""

PROMPT_TEMPLATE = """
You are generating medical multiple-choice questions (MCQ) in JSON only.

Constraints:
- Output MUST be a JSON array of length {n_questions}.
- Do not wrap in markdown or code fences.
- Each item MUST match this schema exactly:
  {{
    "topic": "...",
    "competency": "...",
    "stem": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "answer_key": "A",
    "explanation": "...",
    "evidence": [
      {{"source": "...", "doc_id": "...", "title": "...", "span_text": "..."}}
    ],
    "status": "OK|INSUFFICIENT_EVIDENCE|FAILED_VERIFICATION",
    "meta": {{
      "retrieval": {{"...": "..."}},
      "verification": {{"...": "..."}},
      "timings_ms": {{"...": 0}}
    }}
  }}
- Never output empty objects or omit required keys.
- Never leave stem/options/explanation empty.
- answer_key MUST be a single letter: "A", "B", "C", or "D" (do NOT use "A|B|C|D").

Evidence rules:
- Use only the evidence provided below.
- evidence.span_text MUST be a verbatim quote of up to 5 sentences from one [E#] entry.
- evidence.doc_id MUST match the id shown in the chosen [E#] entry.
- If evidence is insufficient for a question, set status=INSUFFICIENT_EVIDENCE,
  keep the full schema with non-empty placeholders (use the literal text
  "Insufficient evidence." for stem/options/explanation), set evidence=[],
  and still set answer_key to "A".
- For OK items, include at least 1 evidence entry.

Style rules:
- Do NOT mention evidence, citations, or [E#] in the stem or options.
- Avoid meta language such as "according to the evidence" or "based on the evidence".
- Do NOT use source attribution phrases in stems/options (e.g., "according to", "based on", "the study shows", "evidence suggests").
- Write stems as natural exam-style questions or short clinical vignettes.

{few_shot_section}

Topic: {topic}
Competency: {competency}

Evidence:
{evidence_text}
"""


def get_few_shot_example(competency: str) -> str:
    """Ambil contoh few-shot berdasarkan kompetensi."""
    competency_lower = competency.strip().lower()
    return FEW_SHOT_EXAMPLES.get(competency_lower, DEFAULT_EXAMPLE)


def build_prompt(
    topic: str,
    competency: str,
    evidence_text: str,
    n_questions: int,
    extra_instructions: Optional[str] = None,
    include_few_shot: bool = True,
) -> str:
    # Build few-shot section
    if include_few_shot:
        example = get_few_shot_example(competency)
        few_shot_section = f"""
--- EXAMPLE FORMAT ---
Follow this example format and quality standard:
{example}
--- END EXAMPLE ---

NOW GENERATE {n_questions} NEW MCQs FOLLOWING THE ABOVE FORMAT:
"""
    else:
        few_shot_section = ""
    
    prompt = PROMPT_TEMPLATE.format(
        topic=topic.strip(),
        competency=competency.strip(),
        evidence_text=evidence_text.strip(),
        n_questions=n_questions,
        few_shot_section=few_shot_section,
    ).strip()
    
    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional instruction: {extra_instructions.strip()}"
    
    return prompt

