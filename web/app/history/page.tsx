'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'

import Footer from '../../components/Footer'
import Navbar from '../../components/Navbar'
import SectionCard from '../../components/SectionCard'
import { clearHistory, loadHistory, type HistoryEntry } from '../lib/history'

export default function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>([])

  useEffect(() => {
    setEntries(loadHistory())
  }, [])

  const handleClearHistory = () => {
    clearHistory()
    setEntries([])
  }

  const emptyState = (
    <div className='empty-state'>
      <div className='empty-icon' aria-hidden='true'>
        <svg viewBox='0 0 48 48'>
          <circle cx='20' cy='22' r='8' />
          <path d='M26 28l7 7' />
          <rect x='9' y='10' width='30' height='28' rx='8' />
        </svg>
      </div>
      <p className='empty-title'>No history yet.</p>
      <p className='empty-desc'>
        Your generated results will be saved automatically after the run completes.
      </p>
    </div>
  )

  const historyCards = useMemo(() => {
    return entries.map((entry) => {
      const totalQuestions = entry.payload.reduce(
        (sum, item) => sum + Math.max(1, item.n_questions || 1),
        0
      )
      const createdAt = new Date(entry.created_at)
      const timestamp = Number.isNaN(createdAt.getTime())
        ? entry.created_at
        : createdAt.toLocaleString()

      return {
        ...entry,
        totalQuestions,
        timestamp,
      }
    })
  }, [entries])

  return (
    <div className='app-shell'>
      <Navbar />
      <main className='page-body'>
        <div className='container'>
          <SectionCard
            title='Generation History'
            action={
              entries.length ? (
                <button
                  type='button'
                  className='ghost-button is-compact'
                  onClick={handleClearHistory}
                >
                  Clear history
                </button>
              ) : null
            }
          >
            {historyCards.length ? (
              <div className='history-list'>
                {historyCards.map((entry, entryIndex) => (
                  <Link
                    href={`/history/${entry.id}`}
                    className='history-entry-link'
                    key={entry.id}
                  >
                    <article className='history-entry'>
                      <header className='history-header'>
                        <div>
                          <p className='history-title'>
                            Submission #{historyCards.length - entryIndex}
                          </p>
                          <p className='history-meta'>
                            {entry.timestamp} · {entry.payload.length} topic ·{' '}
                            {entry.totalQuestions} questions
                          </p>
                        </div>
                        <span className='history-count'>
                          {entry.results.length} generated
                        </span>
                      </header>

                      <div className='history-topics'>
                        {entry.payload.map((item, index) => (
                          <div
                            className='history-topic'
                            key={`${entry.id}-${index}`}
                          >
                            <p className='history-topic-title'>{item.keyword}</p>
                            <p className='history-topic-meta'>
                              {item.n_questions} questions
                            </p>
                          </div>
                        ))}
                      </div>
                    </article>
                  </Link>
                ))}
              </div>
            ) : (
              emptyState
            )}
          </SectionCard>
        </div>
      </main>
      <Footer />
    </div>
  )
}
