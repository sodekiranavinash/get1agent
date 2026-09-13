import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { availableViews } from './roles'
import {
  readStoredView,
  subscribeViewReset,
  writeStoredView,
  type AppView,
} from './view'

type ViewContextValue = {
  /** The active view, or null while the user still has to choose. */
  view: AppView | null
  available: AppView[]
  canSwitch: boolean
  chooseView: (view: AppView) => void
}

const ViewContext = createContext<ViewContextValue | null>(null)

export function ViewProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth0()
  const available = useMemo(() => availableViews(user), [user])
  const [stored, setStored] = useState<AppView | null>(readStoredView)

  // A fresh login clears the stored view; reset our in-memory copy too.
  useEffect(() => subscribeViewReset(() => setStored(null)), [])

  const view = useMemo<AppView | null>(() => {
    if (stored && available.includes(stored)) return stored
    if (available.length === 1) return available[0]
    return null
  }, [stored, available])

  const chooseView = useCallback((next: AppView) => {
    writeStoredView(next)
    setStored(next)
  }, [])

  const value = useMemo(
    () => ({
      view,
      available,
      canSwitch: available.length > 1,
      chooseView,
    }),
    [view, available, chooseView],
  )

  return <ViewContext.Provider value={value}>{children}</ViewContext.Provider>
}

export function useView(): ViewContextValue {
  const context = useContext(ViewContext)
  if (!context) {
    throw new Error('useView must be used within ViewProvider')
  }
  return context
}
