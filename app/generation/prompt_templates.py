from __future__ import annotations

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
    "answer_key": "A|B|C|D",
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

Evidence rules:
- Use only the evidence provided below.
- evidence.span_text MUST be a verbatim quote of 1-2 sentences from one [E#] entry.
- If evidence is insufficient for a question, set status=INSUFFICIENT_EVIDENCE,
  provide empty strings for stem/options/explanation as needed, and set evidence=[].
- For OK items, include at least 1 evidence entry.

Style rules:
- Do NOT mention evidence, citations, or [E#] in the stem or options.
- Avoid meta language such as "according to the evidence" or "based on the evidence".
- Write stems as natural exam-style questions or short clinical vignettes.

Topic: {topic}
Competency: {competency}

Evidence:
{evidence_text}
"""


def build_prompt(
    topic: str,
    competency: str,
    evidence_text: str,
    n_questions: int,
    extra_instructions: str | None = None,
) -> str:
    prompt = PROMPT_TEMPLATE.format(
        topic=topic.strip(),
        competency=competency.strip(),
        evidence_text=evidence_text.strip(),
        n_questions=n_questions,
    ).strip()
    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional instruction: {extra_instructions.strip()}"
    return prompt
