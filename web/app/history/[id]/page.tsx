'use client'

import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'

import Footer from '../../../components/Footer'
import Navbar from '../../../components/Navbar'
import QuestionCard from '../../../components/QuestionCard'
import SectionCard from '../../../components/SectionCard'
import { loadHistory, type HistoryEntry } from '../../lib/history'
import { exportDOCX, exportJSON, exportPDF } from '../../lib/export'
import {
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
  const [exportOpen, setExportOpen] = useState(false)
  const [displayLanguage, setDisplayLanguage] = useState<DisplayLanguage>('en')
  const exportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const all = loadHistory()
    const found = all.find((item) => item.id === params.id) || null
    setEntry(found)
    setIsReady(true)
  }, [params.id])

  // Close export dropdown on outside click
  useEffect(() => {
    if (!exportOpen) return
    const handler = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [exportOpen])

  const summary = useMemo(() => {
    if (!entry) {
      return null
    }
    const totalQuestions = entry.payload.reduce(
      (sum, item) => sum + Math.max(1, item.n_questions || 1),
      0
    )
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
    setExportOpen(false)
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
                  <div
                    className='language-selector'
                    role='group'
                    aria-label='Display language'
                  >
                    <label
                      className={`lang-radio-label${displayLanguage === 'en' ? ' active' : ''}`}
                    >
                      <input
                        type='radio'
                        name='history-display-language'
                        value='en'
                        checked={displayLanguage === 'en'}
                        onChange={() => setDisplayLanguage('en')}
                        className='lang-radio-input'
                      />
                      🇬🇧 EN
                    </label>
                    <label
                      className={`lang-radio-label${displayLanguage === 'id' ? ' active' : ''}`}
                    >
                      <input
                        type='radio'
                        name='history-display-language'
                        value='id'
                        checked={displayLanguage === 'id'}
                        onChange={() => setDisplayLanguage('id')}
                        className='lang-radio-input'
                      />
                      🇮🇩 ID
                    </label>
                  </div>
                ) : null}
                {entry && entry.results.length > 0 ? (
                  <div className='export-dropdown' ref={exportRef}>
                    <button
                      id='history-export-btn'
                      type='button'
                      className='export-trigger'
                      onClick={() => setExportOpen((o) => !o)}
                      aria-haspopup='true'
                      aria-expanded={exportOpen}
                    >
                      <span>⬇</span> Export
                    </button>
                    {exportOpen ? (
                      <div className='export-menu' role='menu'>
                        <button
                          id='history-export-json-btn'
                          type='button'
                          className='export-menu-item'
                          role='menuitem'
                          onClick={() => handleExport('json')}
                        >
                          <span className='export-icon'>{}</span>
                          <span>
                            <strong>JSON</strong>
                            <small>Raw data</small>
                          </span>
                        </button>
                        <button
                          id='history-export-pdf-btn'
                          type='button'
                          className='export-menu-item'
                          role='menuitem'
                          onClick={() => handleExport('pdf')}
                        >
                          <span className='export-icon'>📕</span>
                          <span>
                            <strong>PDF</strong>
                            <small>Print-ready exam</small>
                          </span>
                        </button>
                        <button
                          id='history-export-docx-btn'
                          type='button'
                          className='export-menu-item'
                          role='menuitem'
                          onClick={() => handleExport('docx')}
                        >
                          <span className='export-icon'>📘</span>
                          <span>
                            <strong>DOCX</strong>
                            <small>Editable document</small>
                          </span>
                        </button>
                      </div>
                    ) : null}
                  </div>
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
                        <p className='history-topic-title'>{item.topic}</p>
                        <p className='history-topic-meta'>
                          {item.competency} · {item.n_questions} questions
                        </p>
                      </div>
                    ))}
                  </div>
                </article>

                {entry.results.length ? (
                  <div className='question-list'>
                    {entry.results.map((question, index) => {
                      const resolved = resolveQuestionForDisplay(question, displayLanguage)
                      const evidenceItems = (resolved.evidence || [])
                        .map((item) => ({
                          docId: item.doc_id || '',
                          source: item.source || '',
                          span: item.span_text || '',
                        }))
                        .filter((item) => item.docId || item.span)

                      return (
                        <QuestionCard
                          key={`${entry.id}-${index}`}
                          index={index + 1}
                          topic={resolved.topic}
                          competency={resolved.competency}
                          prompt={resolved.stem || 'Question text unavailable.'}
                          options={[
                            { key: 'A' as const, text: resolved.options.A || '-' },
                            { key: 'B' as const, text: resolved.options.B || '-' },
                            { key: 'C' as const, text: resolved.options.C || '-' },
                            { key: 'D' as const, text: resolved.options.D || '-' },
                          ]}
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
