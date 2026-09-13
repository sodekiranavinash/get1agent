import { useCallback, useEffect, useRef, useState } from 'react'

type AdaptivePollOptions = {
  /** Polling only runs while this is true (e.g. activity panel open + work active). */
  enabled: boolean
  /** Called on every poll tick. Kept in a ref, so it does not need to be stable. */
  onPoll: () => void
  /** First delay after activity starts. */
  baseMs?: number
  /** Longest delay the backoff will reach. */
  maxMs?: number
  /** Stop polling after roughly this much time spent actively polling. */
  capMs?: number
  /** When this value changes, new data arrived: poll fast again. */
  resetKey?: unknown
}

type AdaptivePollResult = {
  /** True once the cap was reached; polling has stopped until `reset()`. */
  cappedOut: boolean
  /** Clear the cap and restart polling immediately. */
  reset: () => void
}

/**
 * Cost-aware polling for live data.
 *
 * - No requests at all while `enabled` is false (callers gate on the panel being
 *   open, so a closed panel costs nothing).
 * - Backs off 2s -> 4s -> 8s -> 15s while a stage is slow, and resets to the base
 *   delay when `resetKey` changes (a new event arrived).
 * - Pauses while the browser tab is hidden; one immediate poll on return.
 * - Stops after `capMs` of active polling so a stuck document cannot poll forever.
 */
export function useAdaptivePoll({
  enabled,
  onPoll,
  baseMs = 2000,
  maxMs = 15000,
  capMs = 10 * 60 * 1000,
  resetKey,
}: AdaptivePollOptions): AdaptivePollResult {
  const [cappedOut, setCappedOut] = useState(false)
  const [restartToken, setRestartToken] = useState(0)
  const onPollRef = useRef(onPoll)
  const delayRef = useRef(baseMs)
  const elapsedRef = useRef(0)
  const wasEnabledRef = useRef(false)
  const lastResetKeyRef = useRef(resetKey)

  useEffect(() => {
    onPollRef.current = onPoll
  })

  // A new event landed: drop back to the fast delay (cap timer keeps running).
  useEffect(() => {
    if (lastResetKeyRef.current === resetKey) return
    lastResetKeyRef.current = resetKey
    delayRef.current = baseMs
    setRestartToken((token) => token + 1)
  }, [resetKey, baseMs])

  const reset = useCallback(() => {
    delayRef.current = baseMs
    elapsedRef.current = 0
    setCappedOut(false)
    setRestartToken((token) => token + 1)
  }, [baseMs])

  useEffect(() => {
    const justEnabled = enabled && !wasEnabledRef.current
    wasEnabledRef.current = enabled

    if (!enabled) {
      delayRef.current = baseMs
      elapsedRef.current = 0
      setCappedOut(false)
      return
    }

    let cancelled = false
    let timer: number | undefined

    const schedule = () => {
      if (cancelled) return
      timer = window.setTimeout(tick, delayRef.current)
    }

    const tick = () => {
      if (cancelled) return
      if (document.visibilityState === 'hidden') {
        // Paused while hidden: no request, just re-check after this delay.
        schedule()
        return
      }
      if (elapsedRef.current >= capMs) {
        setCappedOut(true)
        return
      }
      onPollRef.current()
      elapsedRef.current += delayRef.current
      delayRef.current = Math.min(maxMs, delayRef.current * 2)
      schedule()
    }

    const onVisibilityChange = () => {
      if (cancelled || document.visibilityState !== 'visible') return
      if (elapsedRef.current >= capMs) return
      if (timer !== undefined) window.clearTimeout(timer)
      delayRef.current = baseMs
      onPollRef.current()
      elapsedRef.current += delayRef.current
      schedule()
    }

    if (justEnabled) {
      // First poll the moment polling is switched on.
      onPollRef.current()
      elapsedRef.current += delayRef.current
      delayRef.current = Math.min(maxMs, delayRef.current * 2)
    }
    schedule()
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [enabled, baseMs, maxMs, capMs, restartToken])

  return { cappedOut, reset }
}
