export type QuestionStatus =
  | "OK"
  | "INSUFFICIENT_EVIDENCE"
  | "FAILED_VERIFICATION"
export type AnswerKey = "A" | "B" | "C" | "D"

export type EvidenceItem = {
  source: string
  doc_id: string
  title: string
  span_text: string
}

export type Options = {
  A: string
  B: string
  C: string
  D: string
}

export type ApiQuestion = {
  topic?: string
  competency?: string
  stem: string
  options: Options
  answer_key: AnswerKey
  explanation?: string | null
  evidence?: EvidenceItem[]
  status?: QuestionStatus
  stem_id?: string | null
  options_id?: Partial<Options> | null
  explanation_id?: string | null
}

export type ProgressState = {
  completed: number
  total: number
}

export type GeneratorState = {
  results: ApiQuestion[]
  loading: boolean
  error: string
  progress: ProgressState | null
  failedCount: number
}

export type WsEvent =
  | {
      type: "progress"
      completed?: number
      total_questions?: number
    }
  | {
      type: "question"
      question: ApiQuestion
    }
  | {
      type: "question_failed"
      status?: QuestionStatus
      message?: string
    }
  | {
      type: "done"
    }
  | {
      type: "error"
      message?: string
    }

export type GeneratePayloadItem = {
  kb_id: string
  keyword: string
  n_questions: number
  language: "en" | "id" | "both"
}

export const totalQuestionsInPayload = (
  payload: Array<{ n_questions: number }>,
): number =>
  payload.reduce((sum, item) => sum + Math.max(1, item.n_questions || 1), 0)

export const buildGeneratePayload = (
  kbId: string,
  sections: Array<{
    keyword: string
    n_questions: number
  }>,
): GeneratePayloadItem[] => {
  return sections
    .map((item) => ({
      kb_id: kbId,
      keyword: item.keyword.trim(),
      n_questions: Math.max(1, Number(item.n_questions) || 1),
      language: "both" as const,
    }))
    .filter((item) => item.kb_id && item.keyword)
}
