import type { LucideIcon } from 'lucide-react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { motion } from 'framer-motion'
import { Card } from './Card'

type StatCardProps = {
  label: string
  value: string
  change?: string
  trend?: 'up' | 'down' | 'neutral'
  icon: LucideIcon
  iconColor?: string
  delay?: number
}

export function StatCard({
  label,
  value,
  change,
  trend = 'neutral',
  icon: Icon,
  iconColor = 'text-accent',
  delay = 0,
}: StatCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <Card hover className="group relative overflow-hidden">
        <div
          className="pointer-events-none absolute -right-4 -top-4 h-24 w-24 rounded-full bg-accent-soft opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100"
          aria-hidden="true"
        />
        <div className="relative flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-muted">{label}</p>
            <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">
              {value}
            </p>
            {change ? (
              <div className="mt-2 flex items-center gap-1">
                {trend === 'up' ? (
                  <TrendingUp className="h-3.5 w-3.5 text-success" />
                ) : trend === 'down' ? (
                  <TrendingDown className="h-3.5 w-3.5 text-accent" />
                ) : null}
                <span
                  className={`text-xs font-medium ${trend === 'up' ? 'text-success' : trend === 'down' ? 'text-accent' : 'text-muted'}`}
                >
                  {change}
                </span>
              </div>
            ) : null}
          </div>
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft ${iconColor}`}
          >
            <Icon className="h-5 w-5" strokeWidth={1.75} />
          </div>
        </div>
      </Card>
    </motion.div>
  )
}
