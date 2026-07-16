'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import ExportMenu from '../../../components/ExportMenu'
import Footer from '../../../components/Footer'
import LanguageSelector from '../../../components/LanguageSelector'
import Navbar from '../../../components/Navbar'
import QuestionCard from '../../../components/QuestionCard'
import SectionCard from '../../../components/SectionCard'
import { loadHistory, type HistoryEntry } from '../../lib/history'
import { exportDOCX, exportJSON, exportPDF } from '../../lib/export'
import { totalQuestionsInPayload } from '../../lib/generate'
import {
  buildEvidenceItems,
  QUESTION_OPTION_KEYS,
  resolveQuestionForDisplay,
  type DisplayLanguage,
} from '../../lib/question-display'

type HistoryDetailPageProps = {
  params: {
    id: string
  }
}

export default function HistoryDetailPage({ params }: HistoryDetailPageProps) {
  const [entry, setEntry] = useState<HistoryEntry | null>(null)
  const [isReady, setIsReady] = useState(false)
  const [displayLanguage, setDisplayLanguage] = useState<DisplayLanguage>('en')

  useEffect(() => {
    const all = loadHistory()
    const found = all.find((item) => item.id === params.id) || null
    setEntry(found)
    setIsReady(true)
  }, [params.id])

  const summary = useMemo(() => {
    if (!entry) {
      return null
    }
    const totalQuestions = totalQuestionsInPayload(entry.payload)
    const createdAt = new Date(entry.created_at)
    const timestamp = Number.isNaN(createdAt.getTime())
      ? entry.created_at
      : createdAt.toLocaleString()

    return {
      timestamp,
      totalQuestions,
    }
  }, [entry])

  const handleExport = (format: 'json' | 'pdf' | 'docx') => {
    if (!entry) return
    if (format === 'json') exportJSON(entry.results, displayLanguage)
    else if (format === 'pdf') exportPDF(entry.results, displayLanguage)
    else exportDOCX(entry.results, displayLanguage)
  }

  return (
    <div className='app-shell'>
      <Navbar />
      <main className='page-body'>
        <div className='container'>
          <SectionCard
            title='History Detail'
            action={
              <div className='section-actions'>
                <Link href='/history' className='ghost-button is-compact'>
                  Back to history
                </Link>
                {entry && entry.results.length > 0 ? (
                  <LanguageSelector
                    value={displayLanguage}
                    onChange={setDisplayLanguage}
                    name='history-display-language'
                  />
                ) : null}
                {entry && entry.results.length > 0 ? (
                  <ExportMenu idPrefix='history' onExport={handleExport} />
                ) : null}
              </div>
            }
          >
            {!isReady ? (
              <div className='empty-state is-loading'>
                <div className='loading-orbit' aria-hidden='true'>
                  <span className='loading-ring'></span>
                  <span className='loading-ring secondary'></span>
                  <span className='loading-core'></span>
                </div>
                <p className='empty-title'>Loading history...</p>
                <p className='empty-desc'>Reading from local storage.</p>
              </div>
            ) : !entry ? (
              <div className='empty-state'>
                <div className='empty-icon' aria-hidden='true'>
                  <svg viewBox='0 0 48 48'>
                    <circle cx='20' cy='22' r='8' />
                    <path d='M26 28l7 7' />
                    <rect x='9' y='10' width='30' height='28' rx='8' />
                  </svg>
                </div>
                <p className='empty-title'>History entry not found.</p>
                <p className='empty-desc'>
                  The entry might have been cleared from local storage.
                </p>
              </div>
            ) : (
              <div className='history-list'>
                <article className='history-entry'>
                  <header className='history-header'>
                    <div>
                      <p className='history-title'>Submission detail</p>
                      <p className='history-meta'>
                        {summary?.timestamp} · {entry.payload.length} topic ·{' '}
                        {summary?.totalQuestions} questions
                      </p>
                    </div>
                    <span className='history-count'>
                      {entry.results.length} generated
                    </span>
                  </header>

                  <div className='history-topics'>
                    {entry.payload.map((item, index) => (
                      <div className='history-topic' key={`${entry.id}-${index}`}>
                        <p className='history-topic-title'>{item.keyword}</p>
                        <p className='history-topic-meta'>
                          {item.n_questions} questions
                        </p>
                      </div>
                    ))}
                  </div>
                </article>

                {entry.results.length ? (
                  <div className='question-list'>
                    {entry.results.map((question, index) => {
                      const resolved = resolveQuestionForDisplay(question, displayLanguage)
                      const evidenceItems = buildEvidenceItems(resolved.evidence)

                      return (
                        <QuestionCard
                          key={`${entry.id}-${index}`}
                          index={index + 1}
                          prompt={resolved.stem || 'Question text unavailable.'}
                          options={QUESTION_OPTION_KEYS.map((key) => ({
                            key,
                            text: resolved.options[key] || '-',
                          }))}
                          selectedKey={resolved.answer_key}
                          explanation={resolved.explanation || ''}
                          evidence={
                            evidenceItems.length
                              ? {
                                  label: 'Source Evidence / RAG Context',
                                  items: evidenceItems,
                                }
                              : undefined
                          }
                          status={resolved.status}
                        />
                      )
                    })}
                  </div>
                ) : (
                  <div className='history-empty'>No saved questions yet.</div>
                )}
              </div>
            )}
          </SectionCard>
        </div>
      </main>
      <Footer />
    </div>
  )
}
