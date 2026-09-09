import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useMediaQuery } from '../../hooks/useMediaQuery'

const STORAGE_KEY = 'sidebar-collapsed'
const COMPACT_BREAKPOINT = '(max-width: 1023px)'

type SidebarContextValue = {
  collapsed: boolean
  effectiveCollapsed: boolean
  isCompact: boolean
  toggle: () => void
}

const SidebarContext = createContext<SidebarContextValue | null>(null)

const readCollapsed = (): boolean => {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export function SidebarProvider({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const isCompact = useMediaQuery(COMPACT_BREAKPOINT)
  const effectiveCollapsed = collapsed || isCompact

  const toggle = useCallback(() => {
    setCollapsed((current) => {
      const next = !current
      try {
        localStorage.setItem(STORAGE_KEY, String(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }, [])

  const value = useMemo(
    () => ({ collapsed, effectiveCollapsed, isCompact, toggle }),
    [collapsed, effectiveCollapsed, isCompact, toggle],
  )

  return (
    <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>
  )
}

export function useSidebar() {
  const context = useContext(SidebarContext)
  if (!context) {
    throw new Error('useSidebar must be used within SidebarProvider')
  }
  return context
}
