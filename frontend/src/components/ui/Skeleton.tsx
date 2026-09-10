import {
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { Card } from './Card'

type SkeletonProps = {
  className?: string
  style?: CSSProperties
}

export function Skeleton({ className = '', style }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={style}
      aria-hidden="true"
    />
  )
}

const DEFAULT_WIDTHS = ['96%', '88%', '94%', '90%', '97%', '92%']

type SkeletonLinesProps = {
  count?: number
  widths?: string[]
  align?: 'start' | 'center'
  gap?: string
  className?: string
  lineClassName?: string
}

export function SkeletonLines({
  count = DEFAULT_WIDTHS.length,
  widths = DEFAULT_WIDTHS,
  align = 'start',
  gap = 'gap-3',
  className = '',
  lineClassName = 'h-4',
}: SkeletonLinesProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex w-full flex-col ${gap} ${
        align === 'center' ? 'items-center' : ''
      } ${className}`}
    >
      <span className="sr-only">Loading…</span>
      {Array.from({ length: count }).map((_, index) => (
        <Skeleton
          key={index}
          className={`rounded-full ${lineClassName}`}
          style={{ width: widths[index % widths.length] }}
        />
      ))}
    </div>
  )
}

/**
 * Full-page skeleton: fills the available height and shows a number of lines
 * that suits the viewport, so it feels natural at any page size.
 */
export function PageSkeleton({ className = '' }: SkeletonProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [count, setCount] = useState(6)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return

    const compute = () => {
      const next = Math.max(4, Math.min(14, Math.round(el.clientHeight / 56)))
      setCount((current) => (current === next ? current : next))
    }

    compute()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(compute)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const widths = Array.from({ length: count }, (_, index) =>
    index === count - 1 ? '58%' : `${87 + ((index * 5) % 12)}%`,
  )

  return (
    <div
      ref={ref}
      className={`flex min-h-[72vh] w-full flex-col justify-center gap-5 ${className}`}
    >
      {widths.map((width, index) => (
        <Skeleton
          key={index}
          className="h-5 rounded-full sm:h-6"
          style={{ width }}
        />
      ))}
    </div>
  )
}

function Line({ className = '' }: { className?: string }) {
  return <Skeleton className={`rounded-md ${className}`} />
}

/** Skeleton shaped like the real Settings page (header + cards). */
export function SettingsSkeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`w-full ${className}`}
    >
      <span className="sr-only">Loading…</span>

      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="w-full max-w-xl space-y-3">
          <Line className="h-5 w-20 rounded-full" />
          <Line className="h-8 w-48" />
          <Line className="h-4 w-full" />
        </div>
        <Line className="h-10 w-36 rounded-xl" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card padding="lg" className="lg:col-span-2">
          <div className="flex items-center gap-4">
            <Line className="h-16 w-16 rounded-2xl" />
            <div className="space-y-2.5">
              <Line className="h-5 w-40" />
              <Line className="h-4 w-56" />
              <Line className="h-5 w-24 rounded-full" />
            </div>
          </div>
          <div className="mt-6 grid gap-4 border-t border-border pt-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Line className="h-3 w-16" />
              <Line className="h-10 w-full rounded-xl" />
            </div>
            <div className="space-y-2">
              <Line className="h-3 w-16" />
              <Line className="h-10 w-full rounded-xl" />
            </div>
          </div>
        </Card>

        <Card padding="lg" className="h-full">
          <div className="flex items-start gap-3">
            <Line className="h-8 w-8 rounded-lg" />
            <div className="space-y-2">
              <Line className="h-4 w-28" />
              <Line className="h-3 w-44" />
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Line className="h-32 w-full rounded-xl" />
            <Line className="h-32 w-full rounded-xl" />
          </div>
        </Card>

        <Card padding="lg" className="h-full">
          <div className="flex items-start gap-3">
            <Line className="h-8 w-8 rounded-lg" />
            <div className="space-y-2">
              <Line className="h-4 w-36" />
              <Line className="h-3 w-48" />
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <Line className="h-3 w-16" />
            <Line className="h-10 w-full rounded-xl" />
            <Line className="h-3 w-40" />
          </div>
        </Card>

        <Card padding="lg" className="lg:col-span-2">
          <div className="flex items-start gap-3">
            <Line className="h-8 w-8 rounded-lg" />
            <div className="space-y-2">
              <Line className="h-4 w-32" />
              <Line className="h-3 w-56" />
            </div>
          </div>
          <div className="mt-4 divide-y divide-border">
            {[0, 1].map((row) => (
              <div
                key={row}
                className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"
              >
                <div className="flex items-start gap-3">
                  <Line className="h-8 w-8 rounded-lg" />
                  <div className="space-y-2">
                    <Line className="h-4 w-44" />
                    <Line className="h-3 w-64 max-w-full" />
                  </div>
                </div>
                <Line className="h-6 w-11 rounded-full" />
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  )
}
