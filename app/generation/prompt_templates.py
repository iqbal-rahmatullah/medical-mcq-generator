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
