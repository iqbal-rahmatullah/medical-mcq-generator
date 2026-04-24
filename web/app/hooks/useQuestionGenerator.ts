'use client'

import { useEffect, useRef, useState } from 'react'

import type {
  ApiQuestion,
  GeneratePayloadItem,
  GeneratorState,
  ProgressState,
  WsEvent,
} from '../lib/generate'
import { getWsUrl } from '../lib/config'
import { appendHistory, createHistoryEntry } from '../lib/history'

export const useQuestionGenerator = (): GeneratorState & {
  generate: (payload: GeneratePayloadItem[]) => void
  cancel: () => void
} => {
  const [results, setResults] = useState<ApiQuestion[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState<ProgressState | null>(null)
  const [failedCount, setFailedCount] = useState(0)
  const socketRef = useRef<WebSocket | null>(null)
  const runIdRef = useRef(0)
  const historyRef = useRef<{
    entry: ReturnType<typeof createHistoryEntry>
    stored: boolean
  } | null>(null)
  const cancelledRef = useRef(false)

  useEffect(() => {
    return () => {
      if (socketRef.current) {
        socketRef.current.close()
      }
    }
  }, [])

  const resetState = () => {
    setError('')
    setResults([])
    setProgress(null)
    setFailedCount(0)
    setLoading(false)
  }

  const finalizeHistory = (storeEmpty: boolean) => {
    const current = historyRef.current
    if (!current || current.stored || cancelledRef.current) {
      return
    }
    if (!storeEmpty && current.entry.results.length === 0) {
      return
    }
    current.stored = true
    appendHistory(current.entry)
  }

  const generate = (payload: GeneratePayloadItem[]) => {
    resetState()
    cancelledRef.current = false

    if (!payload.length) {
      setError('Topic and competency are required.')
      return
    }

    if (socketRef.current) {
      cancelledRef.current = true
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
    historyRef.current = { entry: createHistoryEntry(payload), stored: false }

    const socket = new WebSocket(getWsUrl('/ws/generate'))
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
        socket.close()
        return
      }

      if (data.type === 'question') {
        setResults((prev) => [...prev, data.question])
        historyRef.current?.entry.results.push(data.question)
      }

      if (data.type === 'question_failed') {
        setFailedCount((prev) => prev + 1)
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
        finalizeHistory(true)
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
      finalizeHistory(false)
      setLoading(false)
    }
  }

  const cancel = () => {
    runIdRef.current += 1
    cancelledRef.current = true
    if (socketRef.current) {
      socketRef.current.close()
      socketRef.current = null
    }
    setLoading(false)
  }

  return {
    results,
    loading,
    error,
    progress,
    failedCount,
    generate,
    cancel,
  }
}
