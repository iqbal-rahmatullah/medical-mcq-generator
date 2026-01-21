'use client'

import { useMemo, useState } from 'react'

import FormField from '../components/FormField'
import Footer from '../components/Footer'
import Navbar from '../components/Navbar'
import QuestionCard from '../components/QuestionCard'
import SectionCard from '../components/SectionCard'
import ToggleSwitch from '../components/ToggleSwitch'
import { useQuestionGenerator } from './hooks/useQuestionGenerator'
import { COMPETENCY_OPTIONS } from './lib/constants'
import type { Options } from './lib/generate'
import { buildGeneratePayload } from './lib/generate'
import type { TopicEntry } from './lib/types'

export default function HomePage() {
  const [topics, setTopics] = useState<TopicEntry[]>([
    {
      id: 'topic-1',
      topic: 'Cardiology',
      competency: 'Diagnosis',
      n_questions: 5,
    },
  ])
  const { results, loading, error, progress, failedCount, generate, cancel } =
    useQuestionGenerator()
  const [showAnswers, setShowAnswers] = useState(true)

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
        topic: question.topic || '',
        competency: question.competency || '',
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

  const handleGenerate = () => {
    const payload = buildGeneratePayload(topics)
    generate(payload)
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
                        {COMPETENCY_OPTIONS.map((option) => (
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
              {loading ? (
                <button
                  type='button'
                  className='secondary-button'
                  onClick={cancel}
                >
                  Stop Generation
                </button>
              ) : null}

              {error ? <p className='form-error'>{error}</p> : null}
              {loading && progress ? (
                <p className='form-muted'>
                  Generating {progress.completed} of {progress.total} questions...
                  {failedCount ? ` ${failedCount} failed validation.` : ''}
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
                <div className='empty-state is-loading'>
                  <div className='loading-orbit' aria-hidden='true'>
                    <span className='loading-ring'></span>
                    <span className='loading-ring secondary'></span>
                    <span className='loading-core'></span>
                  </div>
                  <p className='empty-title'>Generating questions...</p>
                  <p className='empty-desc'>
                    We are streaming results as they are ready.
                  </p>
                  <div className='loading-bar' aria-hidden='true'></div>
                </div>
              ) : results.length ? (
                <div className='question-list'>
                  {questionCards.map((question) => (
                    <QuestionCard
                      key={question.prompt.slice(0, 24)}
                      index={question.index}
                      topic={question.topic}
                      competency={question.competency}
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
