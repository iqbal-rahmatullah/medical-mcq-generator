'use client'

import { useEffect, useRef } from 'react'

export function usePolling(
  active: boolean,
  callback: () => void,
  intervalMs = 2000,
) {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (!active) return
    const id = setInterval(() => callbackRef.current(), intervalMs)
    return () => clearInterval(id)
  }, [active, intervalMs])
}
