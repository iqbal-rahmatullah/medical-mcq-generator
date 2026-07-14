"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"

import FormField from "../../../components/FormField"
import Footer from "../../../components/Footer"
import Navbar from "../../../components/Navbar"
import QuestionCard from "../../../components/QuestionCard"
import SectionCard from "../../../components/SectionCard"
import ToggleSwitch from "../../../components/ToggleSwitch"
import { useQuestionGenerator } from "../../hooks/useQuestionGenerator"
import { exportDOCX, exportJSON, exportPDF } from "../../lib/export"
import { buildGeneratePayload } from "../../lib/generate"
import { getKeywordStats, getKnowledge } from "../../lib/knowledge"
import type { KeywordStat, KnowledgeManifest } from "../../lib/knowledge"
import {
  hasIndonesianTranslationCoverage,
  QUESTION_OPTION_KEYS,
  resolveQuestionForDisplay,
} from "../../lib/question-display"

type KeywordSection = {
  id: string
  keyword: string
  n_questions: number
}

export default function KnowledgeGeneratorPage() {
  const params = useParams<{ kb_id: string }>()
  const kbId = params.kb_id

  const [kb, setKb] = useState<KnowledgeManifest | null>(null)
  const [kbError, setKbError] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [sections, setSections] = useState<KeywordSection[]>([
    { id: "section-1", keyword: "", n_questions: 5 },
  ])
  const { results, loading, error, progress, failedCount, generate, cancel } =
    useQuestionGenerator()
  const [showAnswers, setShowAnswers] = useState(true)
  const [displayLanguage, setDisplayLanguage] = useState<"en" | "id">("en")
  const [exportOpen, setExportOpen] = useState(false)
  const exportRef = useRef<HTMLDivElement>(null)

  const [statsOpen, setStatsOpen] = useState(false)
  const [stats, setStats] = useState<KeywordStat[]>([])
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState("")

  const refreshKb = async () => {
    try {
      const data = await getKnowledge(kbId)
      setKb(data)
      setKbError("")
    } catch (err) {
      setKbError(
        err instanceof Error ? err.message : "Failed to load knowledge base.",
      )
    }
  }

  useEffect(() => {
    refreshKb()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId])

  useEffect(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (kb && kb.status === "processing") {
      pollRef.current = setInterval(refreshKb, 2000)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kb?.status])

  const questionCards = useMemo(() => {
    const rankedQuestions = results
      .map((question, sourceIndex) => ({
        question,
        sourceIndex,
        isCovered:
          displayLanguage !== "id" ||
          hasIndonesianTranslationCoverage(question),
      }))
      .sort((left, right) => {
        if (left.isCovered === right.isCovered) {
          return left.sourceIndex - right.sourceIndex
        }
        return left.isCovered ? -1 : 1
      })

    return rankedQuestions.map(({ question, sourceIndex }, index) => {
      const resolvedQuestion = resolveQuestionForDisplay(
        question,
        displayLanguage,
      )

      const evidenceItems = resolvedQuestion.evidence
        .map((item) => {
          const docId = item.doc_id || ""
          const source = item.source || ""
          const span = item.span_text || ""
          return { docId, source, span }
        })
        .filter((item) => item.docId || item.span)

      return {
        sourceIndex,
        index: index + 1,
        prompt: resolvedQuestion.stem || "Question text unavailable.",
        options: QUESTION_OPTION_KEYS.map((key) => ({
          key,
          text: resolvedQuestion.options[key] || "-",
        })),
        selectedKey: showAnswers ? resolvedQuestion.answer_key : undefined,
        explanation: resolvedQuestion.explanation || "",
        evidence: evidenceItems.length
          ? { label: "Source Evidence / RAG Context", items: evidenceItems }
          : undefined,
        status: resolvedQuestion.status,
      }
    })
  }, [results, showAnswers, displayLanguage])

  const handleSectionChange = (
    id: string,
    field: keyof KeywordSection,
    value: string | number,
  ) => {
    setSections((prev) =>
      prev.map((section) =>
        section.id === id ? { ...section, [field]: value } : section,
      ),
    )
  }

  const handleAddSection = () => {
    setSections((prev) => [
      ...prev,
      { id: `section-${Date.now()}`, keyword: "", n_questions: 5 },
    ])
  }

  const handleRemoveSection = (id: string) => {
    setSections((prev) => prev.filter((section) => section.id !== id))
  }

  const handleGenerate = () => {
    const payload = buildGeneratePayload(kbId, sections)
    generate(payload)
  }

  const openStats = async () => {
    setStatsOpen(true)
    setStatsLoading(true)
    setStatsError("")
    try {
      setStats(await getKeywordStats(kbId, 20))
    } catch (err) {
      setStatsError(err instanceof Error ? err.message : "Failed to load stats.")
    } finally {
      setStatsLoading(false)
    }
  }

  const useKeyword = (word: string) => {
    setStatsOpen(false)
    setSections((prev) => {
      const firstEmpty = prev.find((s) => !s.keyword.trim())
      if (firstEmpty) {
        return prev.map((s) =>
          s.id === firstEmpty.id ? { ...s, keyword: word } : s,
        )
      }
      return [...prev, { id: `section-${Date.now()}`, keyword: word, n_questions: 5 }]
    })
  }

  const maxStatCount = stats.length ? stats[0].count : 1

  const handleExport = (format: "json" | "pdf" | "docx") => {
    setExportOpen(false)
    if (format === "json") exportJSON(results, displayLanguage)
    else if (format === "pdf") exportPDF(results, displayLanguage)
    else exportDOCX(results, displayLanguage)
  }

  useEffect(() => {
    if (!exportOpen) return
    const handler = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [exportOpen])

  return (
    <div className='app-shell'>
      <Navbar />
      <main className='page-body'>
        <div className='container'>
          <div className='kb-breadcrumb'>
            <Link href='/'>Knowledge Bases</Link>
            <span>/</span>
            <span>{kb?.title || kbId}</span>
          </div>

          {kbError ? (
            <div className='kb-guard-state'>
              <p className='empty-title'>Could not load this knowledge base.</p>
              <p className='empty-desc'>{kbError}</p>
              <Link href='/' className='ghost-button'>
                Back to Knowledge Bases
              </Link>
            </div>
          ) : !kb ? (
            <div className='kb-guard-state'>
              <p className='empty-desc'>Loading...</p>
            </div>
          ) : kb.status === "processing" ? (
            <div className='kb-guard-state'>
              <div className='loading-orbit' aria-hidden='true'>
                <span className='loading-ring'></span>
                <span className='loading-ring secondary'></span>
                <span className='loading-core'></span>
              </div>
              <p className='empty-title'>Knowledge base is still processing…</p>
              <p className='empty-desc'>
                {Math.round((kb.progress || 0) * 100)}% complete. This page will
                unlock automatically once ingestion finishes.
              </p>
            </div>
          ) : kb.status === "failed" ? (
            <div className='kb-guard-state'>
              <p className='empty-title'>Ingestion failed for this knowledge base.</p>
              <p className='empty-desc'>{kb.error || "Unknown error."}</p>
              <Link href='/' className='ghost-button'>
                Back to Knowledge Bases
              </Link>
            </div>
          ) : (
            <div className='content-grid'>
              <SectionCard title={`Generate — ${kb.title}`}>
                <p className='kb-header-files'>
                  Source files: {kb.files.join(", ") || "none"} ·{" "}
                  {kb.n_chunks} chunks indexed
                </p>
                <button
                  type='button'
                  className='ghost-button is-compact'
                  onClick={openStats}
                >
                  📊 Keyword Stats
                </button>
                <div className='config-stack'>
                  {sections.map((section, index) => (
                    <div className='config-card' key={section.id}>
                      <div className='config-header'>
                        <p className='config-title'>Keyword {index + 1}</p>
                        {sections.length > 1 ? (
                          <button
                            type='button'
                            className='remove-button'
                            onClick={() => handleRemoveSection(section.id)}
                          >
                            Remove
                          </button>
                        ) : null}
                      </div>
                      <FormField label='Keyword'>
                        <input
                          className='text-input'
                          value={section.keyword}
                          onChange={(event) =>
                            handleSectionChange(
                              section.id,
                              "keyword",
                              event.target.value,
                            )
                          }
                          placeholder='e.g. VLAN segmentation'
                        />
                      </FormField>
                      <FormField label='Question Count'>
                        <input
                          className='text-input'
                          type='number'
                          min={1}
                          value={section.n_questions}
                          onChange={(event) =>
                            handleSectionChange(
                              section.id,
                              "n_questions",
                              Math.max(
                                1,
                                Number.parseInt(event.target.value, 10) || 1,
                              ),
                            )
                          }
                        />
                      </FormField>
                    </div>
                  ))}
                </div>

                <button
                  type='button'
                  className='ghost-button'
                  onClick={handleAddSection}
                >
                  + Add Keyword Section
                </button>

                <button
                  type='button'
                  className='primary-button'
                  onClick={handleGenerate}
                  disabled={loading}
                >
                  {loading ? "Generating..." : "Generate Questions"}
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
                    Generating {progress.completed} of {progress.total}{" "}
                    questions...
                    {failedCount ? ` ${failedCount} failed validation.` : ""}
                  </p>
                ) : null}
              </SectionCard>

              <SectionCard
                title='Generated Questions'
                action={
                  <div className='section-actions'>
                    <div
                      className='language-selector'
                      role='group'
                      aria-label='Display language'
                    >
                      <label
                        className={`lang-radio-label${displayLanguage === "en" ? " active" : ""}`}
                      >
                        <input
                          type='radio'
                          name='display-language'
                          value='en'
                          checked={displayLanguage === "en"}
                          onChange={() => setDisplayLanguage("en")}
                          className='lang-radio-input'
                        />
                        🇬🇧 EN
                      </label>
                      <label
                        className={`lang-radio-label${displayLanguage === "id" ? " active" : ""}`}
                      >
                        <input
                          type='radio'
                          name='display-language'
                          value='id'
                          checked={displayLanguage === "id"}
                          onChange={() => setDisplayLanguage("id")}
                          className='lang-radio-input'
                        />
                        🇮🇩 ID
                      </label>
                    </div>
                    <ToggleSwitch
                      label='Show correct answers'
                      checked={showAnswers}
                      onChange={setShowAnswers}
                    />
                    {results.length > 0 && !loading ? (
                      <div className='export-dropdown' ref={exportRef}>
                        <button
                          id='export-btn'
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
                              id='export-json-btn'
                              type='button'
                              className='export-menu-item'
                              role='menuitem'
                              onClick={() => handleExport("json")}
                            >
                              <span className='export-icon'>{}</span>
                              <span>
                                <strong>JSON</strong>
                                <small>Raw data</small>
                              </span>
                            </button>
                            <button
                              id='export-pdf-btn'
                              type='button'
                              className='export-menu-item'
                              role='menuitem'
                              onClick={() => handleExport("pdf")}
                            >
                              <span className='export-icon'>📕</span>
                              <span>
                                <strong>PDF</strong>
                                <small>Print-ready exam</small>
                              </span>
                            </button>
                            <button
                              id='export-docx-btn'
                              type='button'
                              className='export-menu-item'
                              role='menuitem'
                              onClick={() => handleExport("docx")}
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
                {results.length ? (
                  <div className='question-list'>
                    {questionCards.map((question) => (
                      <QuestionCard
                        key={`question-${question.sourceIndex}`}
                        index={question.index}
                        prompt={question.prompt}
                        options={question.options}
                        selectedKey={question.selectedKey}
                        explanation={question.explanation}
                        evidence={question.evidence}
                        status={question.status}
                      />
                    ))}
                  </div>
                ) : null}

                {loading ? (
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
                ) : null}

                {!loading && !results.length ? (
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
                      Add a keyword on the left and click Generate Questions.
                    </p>
                  </div>
                ) : null}
              </SectionCard>
            </div>
          )}
        </div>
      </main>
      <Footer />

      {statsOpen ? (
        <div className='modal-overlay' onClick={() => setStatsOpen(false)}>
          <div className='modal-panel' onClick={(e) => e.stopPropagation()}>
            <p className='modal-title'>Top Keywords</p>
            <p className='form-muted'>
              Most frequent words in this knowledge base (stopwords excluded).
              Click one to use it as a keyword.
            </p>
            {statsLoading ? (
              <p className='form-muted'>Loading...</p>
            ) : statsError ? (
              <p className='form-error'>{statsError}</p>
            ) : !stats.length ? (
              <p className='form-muted'>No keywords found.</p>
            ) : (
              <div className='kw-stat-list'>
                {stats.map((s) => (
                  <button
                    type='button'
                    className='kw-stat-row'
                    key={s.word}
                    onClick={() => useKeyword(s.word)}
                  >
                    <span className='kw-stat-label'>{s.word}</span>
                    <span
                      className='kw-stat-bar'
                      style={{ width: `${(s.count / maxStatCount) * 100}%` }}
                    />
                    <span className='kw-stat-count'>{s.count}</span>
                  </button>
                ))}
              </div>
            )}
            <div className='modal-actions'>
              <button
                type='button'
                className='primary-button'
                onClick={() => setStatsOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
