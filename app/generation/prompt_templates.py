from __future__ import annotations

from typing import Optional

# Single neutral example (domain-agnostic: source material can be any topic).
DEFAULT_EXAMPLE = """
EXAMPLE MCQ:
{
  "topic": "Computer Networking",
  "stem": "A network engineer needs to reduce broadcast traffic on a large LAN without adding new physical switches. Which approach best achieves this?",
  "options": {
    "A": "Replace all hubs with switches",
    "B": "Segment the LAN into multiple VLANs",
    "C": "Increase the cable length between devices",
    "D": "Disable the spanning tree protocol"
  },
  "answer_key": "B",
  "explanation": "VLANs create separate broadcast domains within the same physical switch infrastructure, reducing broadcast traffic without requiring additional hardware.",
  "evidence": [{"source": "networking_guide.pdf", "doc_id": "networking_guide.pdf#3", "title": "networking_guide.pdf", "span_text": "Segmenting a LAN into VLANs creates separate broadcast domains, which reduces unnecessary broadcast traffic across the network."}],
  "status": "OK"
}
"""

DEFAULT_EXAMPLE_BILINGUAL = """
EXAMPLE MCQ (with Bahasa Indonesia translation):
{
  "topic": "Computer Networking",
  "stem": "A network engineer needs to reduce broadcast traffic on a large LAN without adding new physical switches. Which approach best achieves this?",
  "options": {
    "A": "Replace all hubs with switches",
    "B": "Segment the LAN into multiple VLANs",
    "C": "Increase the cable length between devices",
    "D": "Disable the spanning tree protocol"
  },
  "answer_key": "B",
  "explanation": "VLANs create separate broadcast domains within the same physical switch infrastructure, reducing broadcast traffic without requiring additional hardware.",
  "stem_id": "Seorang network engineer perlu mengurangi broadcast traffic pada LAN besar tanpa menambah switch fisik baru. Pendekatan mana yang paling tepat?",
  "options_id": {
    "A": "Mengganti semua hub dengan switch",
    "B": "Membagi LAN menjadi beberapa VLAN",
    "C": "Menambah panjang kabel antar perangkat",
    "D": "Menonaktifkan spanning tree protocol"
  },
  "explanation_id": "VLAN membuat broadcast domain terpisah dalam infrastruktur switch fisik yang sama, sehingga mengurangi broadcast traffic tanpa perlu perangkat keras tambahan.",
  "evidence": [{"source": "networking_guide.pdf", "doc_id": "networking_guide.pdf#3", "title": "networking_guide.pdf", "span_text": "Segmenting a LAN into VLANs creates separate broadcast domains, which reduces unnecessary broadcast traffic across the network."}],
  "status": "OK"
}
"""

PROMPT_TEMPLATE = """
You are generating multiple-choice questions (MCQ) from the provided source material, in JSON only.

Constraints:
- Output MUST be a JSON array of length {n_questions}.
- Do not wrap in markdown or code fences.
- Each item MUST match this schema exactly:
  {{
    "topic": "...",
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
- Write stems as natural exam-style questions.

CRITICAL RULES:
- The question MUST be DIRECTLY and SPECIFICALLY about "{topic}" — do NOT create questions about other topics even if the evidence mentions them.
- Each question in the batch must test a DIFFERENT concept. Do not create multiple questions about the same fact, mechanism, or finding.
- Do NOT use "All of the above", "None of the above", or "Both A and B" as answer options.

{few_shot_section}

Keyword: {topic}

Evidence:
{evidence_text}
"""

PROMPT_TEMPLATE_BILINGUAL = """
You are generating multiple-choice questions (MCQ) from the provided source material, in JSON only, with dual-language output (English and Bahasa Indonesia).

Constraints:
- Output MUST be a JSON array of length {n_questions}.
- Do not wrap in markdown or code fences.
- Each item MUST match this schema exactly:
  {{
    "topic": "...",
    "stem": "...(English question stem)...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "answer_key": "A",
    "explanation": "...(English explanation)...",
    "stem_id": "...(Terjemahan stem dalam Bahasa Indonesia)...",
    "options_id": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "explanation_id": "...(Penjelasan dalam Bahasa Indonesia)...",
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
- Never leave stem/options/explanation/stem_id/options_id/explanation_id empty.
- answer_key MUST be a single letter: "A", "B", "C", or "D" (do NOT use "A|B|C|D").

Bilingual rules:
- stem, options, explanation MUST be in English.
- stem_id, options_id, explanation_id MUST be accurate, natural Bahasa Indonesia translations.
- Translate domain-specific terms accurately using standard Indonesian terminology for the subject matter.
- If status=INSUFFICIENT_EVIDENCE, set stem_id to "Bukti tidak mencukupi.", options_id same letters with "Bukti tidak mencukupi." values, explanation_id to "Bukti tidak mencukupi."

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
- Do NOT mention evidence, citations, or [E#] in the stem/stem_id or options/options_id.
- Avoid meta language such as "according to the evidence" or "based on the evidence".
- Do NOT use source attribution phrases in stems/options (e.g., "according to", "based on", "the study shows", "evidence suggests").
- Write stems as natural exam-style questions.

CRITICAL RULES:
- The question MUST be DIRECTLY and SPECIFICALLY about "{topic}" — do NOT create questions about other topics even if the evidence mentions them.
- Each question in the batch must test a DIFFERENT concept. Do not create multiple questions about the same fact, mechanism, or finding.
- Do NOT use "All of the above", "None of the above", or "Both A and B" as answer options.
- For Bahasa Indonesia translations (stem_id, options_id, explanation_id): use ONLY standard Latin characters. Do NOT include Chinese, Korean, Japanese, Arabic, or any non-Latin characters.

{few_shot_section}

Keyword: {topic}

Evidence:
{evidence_text}
"""


def get_few_shot_example(bilingual: bool = False) -> str:
    return DEFAULT_EXAMPLE_BILINGUAL if bilingual else DEFAULT_EXAMPLE


def build_prompt(
    topic: str,
    competency: str,
    evidence_text: str,
    n_questions: int,
    extra_instructions: Optional[str] = None,
    include_few_shot: bool = True,
    language: str = "en",
) -> str:
    bilingual = language in ("both", "id")
    template = PROMPT_TEMPLATE_BILINGUAL if bilingual else PROMPT_TEMPLATE

    # Build few-shot section
    if include_few_shot:
        example = get_few_shot_example(bilingual=bilingual)
        few_shot_section = f"""
--- EXAMPLE FORMAT ---
Follow this example format and quality standard:
{example}
--- END EXAMPLE ---

NOW GENERATE {n_questions} NEW MCQs FOLLOWING THE ABOVE FORMAT:
"""
    else:
        few_shot_section = ""

    prompt = template.format(
        topic=topic.strip(),
        competency=competency.strip(),
        evidence_text=evidence_text.strip(),
        n_questions=n_questions,
        few_shot_section=few_shot_section,
    ).strip()

    if extra_instructions:
        prompt = f"{prompt}\n\nAdditional instruction: {extra_instructions.strip()}"

    return prompt

