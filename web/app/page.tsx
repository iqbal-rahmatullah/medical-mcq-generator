"use client"

import { useEffect, useRef, useState } from "react"
import type { MouseEvent } from "react"
import { useRouter } from "next/navigation"

import FormField from "../components/FormField"
import Footer from "../components/Footer"
import Navbar from "../components/Navbar"
import SectionCard from "../components/SectionCard"
import {
  addKnowledgeFiles,
  createKnowledge,
  deleteKnowledge,
  listKnowledge,
  removeKnowledgeFile,
  renameKnowledge,
} from "./lib/knowledge"
import type { KnowledgeManifest } from "./lib/knowledge"

const STATUS_LABEL: Record<KnowledgeManifest["status"], string> = {
  processing: "Embedding Processing",
  ready: "Ready",
  failed: "Failed",
}

export default function HomePage() {
  const router = useRouter()
  const [kbs, setKbs] = useState<KnowledgeManifest[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  const [createOpen, setCreateOpen] = useState(false)
  const [createTitle, setCreateTitle] = useState("")
  const [createFiles, setCreateFiles] = useState<File[]>([])
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")

  const [editingKb, setEditingKb] = useState<KnowledgeManifest | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const [editAddFiles, setEditAddFiles] = useState<File[]>([])
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState("")

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = async () => {
    try {
      const data = await listKnowledge()
      setKbs(data)
      setError("")
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load knowledge bases.",
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  useEffect(() => {
    const hasProcessing = kbs.some((kb) => kb.status === "processing")
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (hasProcessing) {
      pollRef.current = setInterval(refresh, 2000)
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbs])

  const handleCardClick = (kb: KnowledgeManifest) => {
    if (kb.status !== "ready") return
    router.push(`/knowledge/${kb.id}`)
  }

  const openCreate = () => {
    setCreateTitle("")
    setCreateFiles([])
    setCreateError("")
    setCreateOpen(true)
  }

  const submitCreate = async () => {
    if (!createTitle.trim()) {
      setCreateError("Title is required.")
      return
    }
    if (!createFiles.length) {
      setCreateError("Select at least one file.")
      return
    }
    setCreating(true)
    setCreateError("")
    try {
      await createKnowledge(createTitle.trim(), createFiles)
      setCreateOpen(false)
      await refresh()
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Failed to create knowledge base.",
      )
    } finally {
      setCreating(false)
    }
  }

  const openEdit = (kb: KnowledgeManifest, event: MouseEvent) => {
    event.stopPropagation()
    setEditingKb(kb)
    setEditTitle(kb.title)
    setEditAddFiles([])
    setEditError("")
  }

  const closeEdit = () => setEditingKb(null)

  const submitRename = async () => {
    if (!editingKb) return
    if (!editTitle.trim()) {
      setEditError("Title is required.")
      return
    }
    setEditSaving(true)
    setEditError("")
    try {
      const updated = await renameKnowledge(editingKb.id, editTitle.trim())
      setEditingKb(updated)
      await refresh()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Failed to rename.")
    } finally {
      setEditSaving(false)
    }
  }

  const submitAddFiles = async () => {
    if (!editingKb || !editAddFiles.length) return
    setEditSaving(true)
    setEditError("")
    try {
      const updated = await addKnowledgeFiles(editingKb.id, editAddFiles)
      setEditingKb(updated)
      setEditAddFiles([])
      await refresh()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : "Failed to add files.")
    } finally {
      setEditSaving(false)
    }
  }

  const handleRemoveFile = async (filename: string) => {
    if (!editingKb) return
    setEditSaving(true)
    setEditError("")
    try {
      const updated = await removeKnowledgeFile(editingKb.id, filename)
      setEditingKb(updated)
      await refresh()
    } catch (err) {
      setEditError(
        err instanceof Error ? err.message : "Failed to remove file.",
      )
    } finally {
      setEditSaving(false)
    }
  }

  const handleDelete = async (kb: KnowledgeManifest, event: MouseEvent) => {
    event.stopPropagation()
    if (
      !window.confirm(
        `Delete knowledge base "${kb.title}"? This cannot be undone.`,
      )
    ) {
      return
    }
    try {
      await deleteKnowledge(kb.id)
      await refresh()
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to delete knowledge base.",
      )
    }
  }

  return (
    <div className='app-shell'>
      <Navbar />
      <main className='page-body'>
        <div className='container'>
          <SectionCard title='Knowledge Bases'>
            {error ? <p className='form-error'>{error}</p> : null}
            {loading ? (
              <p className='form-muted'>Loading...</p>
            ) : (
              <div className='kb-grid'>
                {kbs.map((kb) => (
                  <div
                    key={kb.id}
                    className={`kb-card${kb.status !== "ready" ? " is-disabled" : ""}`}
                    onClick={() => handleCardClick(kb)}
                  >
                    <div className='kb-card-header'>
                      <span className='kb-card-title'>{kb.title}</span>
                      <div className='kb-card-actions'>
                        <button
                          type='button'
                          className='kb-card-icon-btn'
                          onClick={(e) => openEdit(kb, e)}
                          aria-label='Edit'
                        >
                          Edit
                        </button>
                        <button
                          type='button'
                          className='kb-card-icon-btn'
                          onClick={(e) => handleDelete(kb, e)}
                          aria-label='Delete'
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <span className={`kb-status-badge ${kb.status}`}>
                      {STATUS_LABEL[kb.status]}
                    </span>
                    <ul className='kb-file-list'>
                      {kb.files.map((f) => (
                        <li key={f}>{f}</li>
                      ))}
                    </ul>
                    {kb.status === "failed" && kb.error ? (
                      <p className='form-error'>{kb.error}</p>
                    ) : null}
                  </div>
                ))}

                <button
                  type='button'
                  className='kb-create-card'
                  onClick={openCreate}
                >
                  + Create Knowledge
                </button>
              </div>
            )}
          </SectionCard>
        </div>
      </main>
      <Footer />

      {createOpen ? (
        <div
          className='modal-overlay'
          onClick={() => !creating && setCreateOpen(false)}
        >
          <div className='modal-panel' onClick={(e) => e.stopPropagation()}>
            <p className='modal-title'>Create Knowledge Base</p>
            <FormField label='Title'>
              <input
                className='text-input'
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                placeholder='e.g. Biology Chapter 1-3'
              />
            </FormField>
            <FormField
              label='Files'
              helper='PDF, DOCX, TXT, or MD. You can select more than one.'
            >
              <input
                type='file'
                multiple
                accept='.pdf,.docx,.txt,.md'
                onChange={(e) =>
                  setCreateFiles(Array.from(e.target.files || []))
                }
              />
            </FormField>
            {createFiles.length ? (
              <p className='form-muted'>
                {createFiles.length} file(s) selected
              </p>
            ) : null}
            {createError ? <p className='form-error'>{createError}</p> : null}
            <div className='modal-actions'>
              <button
                type='button'
                className='secondary-button'
                onClick={() => setCreateOpen(false)}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                type='button'
                className='primary-button'
                onClick={submitCreate}
                disabled={creating}
              >
                {creating ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {editingKb ? (
        <div className='modal-overlay' onClick={closeEdit}>
          <div className='modal-panel' onClick={(e) => e.stopPropagation()}>
            <p className='modal-title'>Edit Knowledge Base</p>
            <FormField label='Title'>
              <input
                className='text-input'
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
              />
            </FormField>
            <button
              type='button'
              className='secondary-button'
              onClick={submitRename}
              disabled={editSaving}
            >
              Save Title
            </button>

            <div>
              <p className='form-label'>Files</p>
              {editingKb.files.map((f) => (
                <div className='modal-file-row' key={f}>
                  <span>{f}</span>
                  <button
                    type='button'
                    className='kb-card-icon-btn'
                    onClick={() => handleRemoveFile(f)}
                    disabled={editSaving}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>

            <FormField label='Add files'>
              <input
                type='file'
                multiple
                accept='.pdf,.docx,.txt,.md'
                onChange={(e) =>
                  setEditAddFiles(Array.from(e.target.files || []))
                }
              />
            </FormField>
            {editAddFiles.length ? (
              <button
                type='button'
                className='secondary-button'
                onClick={submitAddFiles}
                disabled={editSaving}
              >
                {editSaving
                  ? "Uploading..."
                  : `Add ${editAddFiles.length} file(s)`}
              </button>
            ) : null}

            {editError ? <p className='form-error'>{editError}</p> : null}

            <div className='modal-actions'>
              <button
                type='button'
                className='primary-button'
                onClick={closeEdit}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
