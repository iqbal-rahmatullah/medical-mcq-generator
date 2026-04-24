import type { ApiQuestion, Options } from "./generate"

export type DisplayLanguage = "en" | "id"

export const QUESTION_OPTION_KEYS = ["A", "B", "C", "D"] as const

const hasText = (value: string | null | undefined): value is string => {
  return typeof value === "string" && value.trim().length > 0
}

export const hasIndonesianTranslationCoverage = (question: ApiQuestion) => {
  return (
    hasText(question.stem_id) &&
    hasText(question.explanation_id) &&
    QUESTION_OPTION_KEYS.every((key) => hasText(question.options_id?.[key]))
  )
}

const pickText = (
  preferred: string | null | undefined,
  fallback: string | null | undefined,
) => {
  if (hasText(preferred)) {
    return preferred
  }
  if (hasText(fallback)) {
    return fallback
  }
  return ""
}

const pickOptionText = (
  options: Partial<Options> | null | undefined,
  key: (typeof QUESTION_OPTION_KEYS)[number],
) => {
  return hasText(options?.[key]) ? options[key] : ""
}

export function resolveQuestionForDisplay(
  question: ApiQuestion,
  lang: DisplayLanguage,
) {
  const useIndonesian = lang === "id"
  const stem = useIndonesian
    ? pickText(question.stem_id, question.stem)
    : pickText(question.stem, question.stem_id)
  const explanation = useIndonesian
    ? pickText(question.explanation_id, question.explanation)
    : pickText(question.explanation, question.explanation_id)

  const options = QUESTION_OPTION_KEYS.reduce<Options>(
    (resolved, key) => {
      const preferred = useIndonesian
        ? pickOptionText(question.options_id, key)
        : pickOptionText(question.options, key)
      const fallback = useIndonesian
        ? pickOptionText(question.options, key)
        : pickOptionText(question.options_id, key)

      resolved[key] = pickText(preferred, fallback)
      return resolved
    },
    { A: "", B: "", C: "", D: "" },
  )

  return {
    stem,
    explanation,
    options,
    topic: question.topic || "",
    competency: question.competency || "",
    answer_key: question.answer_key,
    evidence: question.evidence || [],
    status: question.status,
  }
}
