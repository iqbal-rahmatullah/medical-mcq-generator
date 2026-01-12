'use client'

import { useEffect, useMemo, useRef, useState } from 'react'

import FormField from '../components/FormField'
import Footer from '../components/Footer'
import Navbar from '../components/Navbar'
import QuestionCard from '../components/QuestionCard'
import SectionCard from '../components/SectionCard'
import ToggleSwitch from '../components/ToggleSwitch'

type QuestionStatus = 'OK' | 'INSUFFICIENT_EVIDENCE' | 'FAILED_VERIFICATION'
type AnswerKey = 'A' | 'B' | 'C' | 'D'

type EvidenceItem = {
  source: string
  doc_id: string
  title: string
  span_text: string
}

type Options = {
  A: string
  B: string
  C: string
  D: string
}

type ApiQuestion = {
  stem: string
  options: Options
  answer_key: AnswerKey
  evidence?: EvidenceItem[]
  status?: QuestionStatus
}

type TopicEntry = {
  id: string
  topic: string
  competency: string
  n_questions: number
}

type ProgressState = {
  completed: number
  total: number
}

type WsEvent =
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
      type: 'done'
    }
  | {
      type: 'error'
      message?: string
    }

const competencyOptions = [
  'Diagnosis',
  'Treatment',
  'Therapy',
  'Etiology',
  'Prevention',
  'Prognosis',
  'Screening',
  'Complications',
  'Pathophysiology',
  'Pharmacology',
  'Monitoring',
  'Investigation',
]

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'
const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL || API_BASE.replace(/^http/, 'ws')

export default function HomePage() {
  const [topics, setTopics] = useState<TopicEntry[]>([
    {
      id: 'topic-1',
      topic: 'Cardiology',
      competency: 'Diagnosis',
      n_questions: 5,
    },
  ])
  const [results, setResults] = useState<ApiQuestion[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showAnswers, setShowAnswers] = useState(true)
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const runIdRef = useRef(0)
  const resultsRef = useRef<ApiQuestion[]>([])

  useEffect(() => {
    return () => {
      if (socketRef.current) {
        socketRef.current.close()
      }
    }
  }, [])

  const questionCards = useMemo(() => {
    return results.map((question, index) => {
      const options: Options = question.options || {
        A: '-',
        B: '-',
        C: '-',
        D: '-',
      }
      const evidenceText = (question.evidence || [])
        .map((item) => item.span_text)
        .filter(Boolean)
        .join(' ')

      return {
        index: index + 1,
        prompt: question.stem || 'Question text unavailable.',
        options: [
          { key: 'A' as const, text: options.A || '-' },
          { key: 'B' as const, text: options.B || '-' },
          { key: 'C' as const, text: options.C || '-' },
          { key: 'D' as const, text: options.D || '-' },
        ],
        selectedKey: showAnswers ? question.answer_key : undefined,
        evidence: evidenceText
          ? {
              label: 'Source Evidence / RAG Context',
              source: evidenceText,
            }
          : undefined,
        status: question.status,
      }
    })
  }, [results, showAnswers])

  const handleTopicChange = (
    id: string,
    field: keyof TopicEntry,
    value: string | number
  ) => {
    setTopics((prev) =>
      prev.map((topic) =>
        topic.id === id ? { ...topic, [field]: value } : topic
      )
    )
  }

  const handleAddTopic = () => {
    setTopics((prev) => [
      ...prev,
      {
        id: `topic-${Date.now()}`,
        topic: '',
        competency: 'Diagnosis',
        n_questions: 5,
      },
    ])
  }

  const handleRemoveTopic = (id: string) => {
    setTopics((prev) => prev.filter((topic) => topic.id !== id))
  }

  const buildPayload = () => {
    return topics
      .map((item) => ({
        topic: item.topic.trim(),
        competency: item.competency.trim(),
        n_questions: Math.max(1, Number(item.n_questions) || 1),
      }))
      .filter((item) => item.topic && item.competency)
  }

  const handleGenerate = () => {
    setError('')
    setResults([])
    resultsRef.current = []
    setProgress(null)
    const payload = buildPayload()

    if (!payload.length) {
      setError('Topik dan kompetensi wajib diisi.')
      return
    }

    if (socketRef.current) {
      socketRef.current.close()
    }

    runIdRef.current += 1
    const currentRunId = runIdRef.current

    const totalQuestions = payload.reduce(
      (sum, item) => sum + Math.max(1, item.n_questions || 1),
      0
    )

    setLoading(true)
    setProgress({ completed: 0, total: totalQuestions })

    const socket = new WebSocket(`${WS_BASE}/ws/generate`)
    socketRef.current = socket

    socket.onopen = () => {
      socket.send(JSON.stringify(payload))
    }

    socket.onmessage = (event) => {
      if (currentRunId !== runIdRef.current) {
        return
      }
      let data: WsEvent
      try {
        data = JSON.parse(event.data) as WsEvent
      } catch (parseError) {
        setError('Invalid websocket message.')
        setLoading(false)
        return
      }

      if (data.type === 'question') {
        resultsRef.current = [...resultsRef.current, data.question]
        setResults(resultsRef.current)
      }

      if (data.type === 'progress') {
        setProgress((prev) => {
          const total = data.total_questions ?? prev?.total ?? totalQuestions
          const completed = data.completed ?? prev?.completed ?? 0
          return { completed, total }
        })
      }

      if (data.type === 'error') {
        setError(data.message || 'Websocket error.')
      }

      if (data.type === 'done') {
        setLoading(false)
        socket.close()
      }
    }

    socket.onerror = () => {
      if (currentRunId !== runIdRef.current) {
        return
      }
      setError('Websocket connection failed.')
      setLoading(false)
    }

    socket.onclose = () => {
      if (currentRunId !== runIdRef.current) {
        return
      }
      setLoading(false)
    }
  }

  return (
    <div className='app-shell'>
      <Navbar />
      <main className='page-body'>
        <div className='container'>
          <div className='content-grid'>
            <SectionCard title='Exam Configuration'>
              <div className='config-stack'>
                {topics.map((topic, index) => (
                  <div className='config-card' key={topic.id}>
                    <div className='config-header'>
                      <p className='config-title'>Topic {index + 1}</p>
                      {topics.length > 1 ? (
                        <button
                          type='button'
                          className='remove-button'
                          onClick={() => handleRemoveTopic(topic.id)}
                        >
                          Remove
                        </button>
                      ) : null}
                    </div>
                    <FormField label='Topic'>
                      <input
                        className='text-input'
                        value={topic.topic}
                        onChange={(event) =>
                          handleTopicChange(
                            topic.id,
                            'topic',
                            event.target.value
                          )
                        }
                        placeholder='Cardiology'
                      />
                    </FormField>
                    <FormField label='Competency'>
                      <select
                        className='text-input'
                        value={topic.competency}
                        onChange={(event) =>
                          handleTopicChange(
                            topic.id,
                            'competency',
                            event.target.value
                          )
                        }
                      >
                        {competencyOptions.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </FormField>
                    <FormField label='Question Count'>
                      <input
                        className='text-input'
                        type='number'
                        min={1}
                        value={topic.n_questions}
                        onChange={(event) =>
                          handleTopicChange(
                            topic.id,
                            'n_questions',
                            Math.max(
                              1,
                              Number.parseInt(event.target.value, 10) || 1
                            )
                          )
                        }
                      />
                    </FormField>
                  </div>
                ))}
              </div>

              <button type='button' className='ghost-button' onClick={handleAddTopic}>
                + Add Another Topic
              </button>

              <button
                type='button'
                className='primary-button'
                onClick={handleGenerate}
                disabled={loading}
              >
                {loading ? 'Generating...' : 'Generate Questions'}
              </button>

              {error ? <p className='form-error'>{error}</p> : null}
              {loading && progress ? (
                <p className='form-muted'>
                  Generating {progress.completed} of {progress.total} questions...
                </p>
              ) : null}
            </SectionCard>

            <SectionCard
              title='Generated Questions'
              action={
                <ToggleSwitch
                  label='Show correct answers'
                  checked={showAnswers}
                  onChange={setShowAnswers}
                />
              }
            >
              {!results.length && loading ? (
                <div className='empty-state'>
                  <div className='empty-icon' aria-hidden='true'>
                    <svg viewBox='0 0 48 48'>
                      <circle cx='20' cy='22' r='8' />
                      <path d='M26 28l7 7' />
                      <rect x='9' y='10' width='30' height='28' rx='8' />
                    </svg>
                  </div>
                  <p className='empty-title'>Generating questions...</p>
                  <p className='empty-desc'>
                    We are streaming results as they are ready.
                  </p>
                </div>
              ) : results.length ? (
                <div className='question-list'>
                  {questionCards.map((question) => (
                    <QuestionCard
                      key={question.prompt.slice(0, 24)}
                      index={question.index}
                      prompt={question.prompt}
                      options={question.options}
                      selectedKey={question.selectedKey}
                      evidence={question.evidence}
                      status={question.status}
                    />
                  ))}
                </div>
              ) : (
                <div className='empty-state'>
                  <div className='empty-icon' aria-hidden='true'>
                    <svg viewBox='0 0 48 48'>
                      <circle cx='20' cy='22' r='8' />
                      <path d='M26 28l7 7' />
                      <rect x='9' y='10' width='30' height='28' rx='8' />
                    </svg>
                  </div>
                  <p className='empty-title'>No questions yet.</p>
                  <p className='empty-desc'>
                    Add a topic on the left and click Generate Questions.
                  </p>
                </div>
              )}
            </SectionCard>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  )
}
