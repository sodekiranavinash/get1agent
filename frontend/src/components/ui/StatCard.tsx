import type { LucideIcon } from 'lucide-react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { Sparkline } from './Sparkline'

type StatCardProps = {
  label: string
  value: string
  change?: string
  trend?: 'up' | 'down' | 'neutral'
  icon: LucideIcon
  iconColor?: string
  spark?: number[]
}

export function StatCard({
  label,
  value,
  change,
  trend = 'neutral',
  icon: Icon,
  iconColor = 'text-accent',
  spark,
}: StatCardProps) {
  return (
    <div className="group relative overflow-hidden rounded-lg border border-border bg-surface p-3.5 transition-colors hover:border-border-strong">
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-xs font-medium text-muted">{label}</p>
        <span
          className={`flex size-7 shrink-0 items-center justify-center rounded-md bg-raised ${iconColor}`}
        >
          <Icon className="size-3.5" strokeWidth={1.75} />
        </span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="text-xl font-semibold tracking-tight text-foreground">
          {value}
        </p>
        {spark ? <Sparkline data={spark} className="text-accent/70" /> : null}
      </div>
      {change ? (
        <div className="mt-1 flex items-center gap-1">
          {trend === 'up' ? (
            <TrendingUp className="size-3.5 text-success" />
          ) : trend === 'down' ? (
            <TrendingDown className="size-3.5 text-accent" />
          ) : null}
          <span
            className={`truncate text-[11px] ${
              trend === 'up'
                ? 'text-success'
                : trend === 'down'
                  ? 'text-accent'
                  : 'text-subtle'
            }`}
          >
            {change}
          </span>
        </div>
      ) : null}
    </div>
  )
}
