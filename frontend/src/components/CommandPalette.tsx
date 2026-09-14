import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search } from 'lucide-react'
import { sidebarLinks } from '../navigation/sidebarLinks'

const CommandPaletteDialog = lazy(() => import('./CommandPaletteDialog'))

type CommandPaletteProps = {
  /** Extra destinations appended after the main navigation (e.g. admin). */
  extraLinks?: { label: string; to: string; section?: string }[]
}

export function CommandPalette({ extraLinks = [] }: CommandPaletteProps) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  const destinations = useMemo(() => {
    const main = sidebarLinks.flatMap((link) =>
      link.children?.length
        ? link.children.map((child) => ({
            label: `${link.label} · ${child.label}`,
            to: child.to,
          }))
        : [{ label: link.label, to: link.to }],
    )
    return [...main, ...extraLinks.map(({ label, to }) => ({ label, to }))]
  }, [extraLinks])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'k' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        setOpen((current) => !current)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const go = (to: string) => {
    setOpen(false)
    navigate(to)
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="group flex h-9 w-full max-w-[320px] items-center gap-2.5 rounded-md border border-border bg-raised/40 px-3 text-left text-[13px] text-subtle transition-colors hover:border-border-strong hover:bg-raised hover:text-muted"
      >
        <Search className="size-[18px] shrink-0" />
        <span className="flex-1 truncate">Search or jump to…</span>
        <kbd className="hidden shrink-0 rounded border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-subtle sm:inline-block">
          ⌘K
        </kbd>
      </button>

      {open ? (
        <Suspense fallback={null}>
          <CommandPaletteDialog
            open={open}
            onOpenChange={setOpen}
            destinations={destinations}
            onNavigate={go}
          />
        </Suspense>
      ) : null}
    </>
  )
}
