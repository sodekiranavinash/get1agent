import { useEffect, useState } from 'react'
import { isDemoMode, subscribeDemo } from './demo'

/** Reactive read-only demo flag (backed by localStorage). */
export function useDemoMode(): boolean {
  const [demo, setDemo] = useState(isDemoMode)
  useEffect(() => subscribeDemo(() => setDemo(isDemoMode())), [])
  return demo
}
