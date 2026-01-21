export type QuestionStatus = 'OK' | 'INSUFFICIENT_EVIDENCE' | 'FAILED_VERIFICATION'
export type AnswerKey = 'A' | 'B' | 'C' | 'D'

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
  evidence?: EvidenceItem[]
  status?: QuestionStatus
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
      type: 'progress'
      completed?: number
      total_questions?: number
    }
  | {
      type: 'question'
      question: ApiQuestion
    }
  | {
      type: 'question_failed'
      status?: QuestionStatus
      message?: string
    }
  | {
      type: 'done'
    }
  | {
      type: 'error'
      message?: string
    }

export type GeneratePayloadItem = {
  topic: string
  competency: string
  n_questions: number
}

export const buildGeneratePayload = (
  topics: Array<{
    topic: string
    competency: string
    n_questions: number
  }>
): GeneratePayloadItem[] => {
  return topics
    .map((item) => ({
      topic: item.topic.trim(),
      competency: item.competency.trim(),
      n_questions: Math.max(1, Number(item.n_questions) || 1),
    }))
    .filter((item) => item.topic && item.competency)
}
