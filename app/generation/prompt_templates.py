from __future__ import annotations

from typing import Optional

# Few-shot examples dengan multiple format variations
FEW_SHOT_EXAMPLES = {
    "basic_sciences": """
EXAMPLE MCQs (Basic Sciences) - Use varied formats like these:

Format 1 - Direct Question:
{
  "stem": "What is the primary function of the Na+/K+-ATPase pump in maintaining cellular homeostasis?",
  "options": {"A": "Generate action potentials", "B": "Maintain resting membrane potential", "C": "Facilitate glucose uptake", "D": "Produce ATP"},
  "answer_key": "B"
}

Format 2 - Mechanism-based:
{
  "stem": "Which mechanism explains why competitive enzyme inhibitors increase the apparent Km without affecting Vmax?",
  "options": {"A": "They decrease enzyme concentration", "B": "They compete with substrate for active site binding", "C": "They alter enzyme conformation permanently", "D": "They increase product formation"},
  "answer_key": "B"
}

Format 3 - Lab/Research Context:
{
  "stem": "A biochemistry student observes that adding excess substrate to an enzyme reaction does not increase velocity beyond a certain point. This observation demonstrates which principle?",
  "options": {"A": "Allosteric inhibition", "B": "Enzyme saturation kinetics", "C": "Competitive inhibition", "D": "Irreversible inhibition"},
  "answer_key": "B"
}
""",
    "clinical_practice": """
EXAMPLE MCQs (Clinical Practice) - Use varied formats like these:

Format 1 - Best Next Step:
{
  "stem": "What is the most appropriate next step for a patient with newly diagnosed type 2 diabetes and HbA1c of 7.5%?",
  "options": {"A": "Start insulin therapy", "B": "Lifestyle modification plus metformin", "C": "Add sulfonylurea", "D": "Refer to endocrinologist"},
  "answer_key": "B"
}

Format 2 - Clinical Vignette:
{
  "stem": "A 58-year-old woman with type 2 diabetes and CKD (eGFR 45 mL/min) needs additional glycemic control. Which agent provides both glycemic and renal benefits?",
  "options": {"A": "Glipizide", "B": "SGLT2 inhibitor", "C": "Pioglitazone", "D": "Sulfonylurea"},
  "answer_key": "B"
}

Format 3 - Guideline-based:
{
  "stem": "According to current guidelines, which first-line therapy is recommended for patients with heart failure with reduced ejection fraction?",
  "options": {"A": "Calcium channel blockers", "B": "ACE inhibitors or ARBs", "C": "Digoxin", "D": "Nitrates"},
  "answer_key": "B"
}
""",
    "pathology": """
EXAMPLE MCQs (Pathology) - Use varied formats like these:

Format 1 - Histologic Description:
{
  "stem": "A biopsy shows granulomas with central caseating necrosis surrounded by epithelioid histiocytes and Langhans giant cells. What is the most likely diagnosis?",
  "options": {"A": "Sarcoidosis", "B": "Tuberculosis", "C": "Foreign body reaction", "D": "Rheumatoid nodule"},
  "answer_key": "B"
}

Format 2 - Direct Question:
{
  "stem": "Which type of necrosis is characteristically seen in acute pancreatitis?",
  "options": {"A": "Coagulative necrosis", "B": "Liquefactive necrosis", "C": "Fat necrosis", "D": "Fibrinoid necrosis"},
  "answer_key": "C"
}

Format 3 - Marker/Staining:
{
  "stem": "Which immunohistochemical marker is most useful for identifying cells of neural crest origin in neuroendocrine tumors?",
  "options": {"A": "Cytokeratin", "B": "Chromogranin A", "C": "Vimentin", "D": "Desmin"},
  "answer_key": "B"
}
""",
    "treatment": """
EXAMPLE MCQs (Treatment) - Use varied formats like these:

Format 1 - First-line Therapy:
{
  "stem": "What is the recommended first-line treatment for mild persistent asthma in adults?",
  "options": {"A": "Short-acting beta-agonist only", "B": "Low-dose inhaled corticosteroid", "C": "Long-acting beta-agonist", "D": "Oral corticosteroids"},
  "answer_key": "B"
}

Format 2 - Drug Selection:
{
  "stem": "Which antihypertensive medication class is preferred in a patient with diabetes and proteinuria?",
  "options": {"A": "Thiazide diuretics", "B": "ACE inhibitors", "C": "Calcium channel blockers", "D": "Beta-blockers"},
  "answer_key": "B"
}

Format 3 - Contraindication/Caution:
{
  "stem": "Metformin should be temporarily discontinued in patients undergoing which procedure?",
  "options": {"A": "Routine blood draw", "B": "Contrast-enhanced CT scan", "C": "Electrocardiogram", "D": "Chest X-ray"},
  "answer_key": "B"
}
""",
    "etiology": """
EXAMPLE MCQs (Etiology) - Use varied formats like these:

Format 1 - Most Common Cause:
{
  "stem": "What is the most common cause of community-acquired pneumonia in adults?",
  "options": {"A": "Haemophilus influenzae", "B": "Streptococcus pneumoniae", "C": "Mycoplasma pneumoniae", "D": "Staphylococcus aureus"},
  "answer_key": "B"
}

Format 2 - Risk Factor:
{
  "stem": "Which factor most significantly increases the risk of developing colorectal cancer?",
  "options": {"A": "High-fiber diet", "B": "Family history of adenomatous polyps", "C": "Regular exercise", "D": "Aspirin use"},
  "answer_key": "B"
}

Format 3 - Pathogen/Agent:
{
  "stem": "Which organism is the primary etiologic agent of peptic ulcer disease?",
  "options": {"A": "Escherichia coli", "B": "Helicobacter pylori", "C": "Campylobacter jejuni", "D": "Clostridium difficile"},
  "answer_key": "B"
}
""",
    "diagnosis": """
EXAMPLE MCQs (Diagnosis) - Use varied formats like these:

Format 1 - Most Sensitive Test:
{
  "stem": "What is the most sensitive initial test for detecting iron deficiency anemia?",
  "options": {"A": "Serum iron", "B": "Serum ferritin", "C": "Total iron-binding capacity", "D": "Hemoglobin level"},
  "answer_key": "B"
}

Format 2 - Gold Standard:
{
  "stem": "Which diagnostic modality is considered the gold standard for diagnosing pulmonary embolism?",
  "options": {"A": "Chest X-ray", "B": "CT pulmonary angiography", "C": "D-dimer", "D": "Ventilation-perfusion scan"},
  "answer_key": "B"
}

Format 3 - Clinical Finding:
{
  "stem": "Which physical examination finding is most specific for acute appendicitis?",
  "options": {"A": "Diffuse abdominal tenderness", "B": "Rebound tenderness at McBurney's point", "C": "Hyperactive bowel sounds", "D": "Abdominal distension"},
  "answer_key": "B"
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

