import type { ApiQuestion, GeneratePayloadItem } from './generate'

export type HistoryEntry = {
  id: string
  created_at: string
  payload: GeneratePayloadItem[]
  results: ApiQuestion[]
}

const STORAGE_KEY = 'aqg_history_v1'
const MAX_ENTRIES = 50

const buildId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `run-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

const safeParse = (raw: string): HistoryEntry[] => {
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter((entry) => {
      if (!entry || typeof entry !== 'object') {
        return false
      }
      return (
        typeof entry.id === 'string' &&
        typeof entry.created_at === 'string' &&
        Array.isArray(entry.payload) &&
        Array.isArray(entry.results)
      )
    }) as HistoryEntry[]
  } catch {
    return []
  }
}

export const createHistoryEntry = (
  payload: GeneratePayloadItem[]
): HistoryEntry => {
  return {
    id: buildId(),
    created_at: new Date().toISOString(),
    payload,
    results: [],
  }
}

export const loadHistory = (): HistoryEntry[] => {
  if (typeof window === 'undefined') {
    return []
  }
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return []
  }
  return safeParse(raw).slice(0, MAX_ENTRIES)
}

export const saveHistory = (entries: HistoryEntry[]) => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(entries.slice(0, MAX_ENTRIES))
  )
}

export const appendHistory = (entry: HistoryEntry): HistoryEntry[] => {
  const existing = loadHistory()
  const next = [entry, ...existing].slice(0, MAX_ENTRIES)
  saveHistory(next)
  return next
}

export const clearHistory = () => {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.removeItem(STORAGE_KEY)
}
