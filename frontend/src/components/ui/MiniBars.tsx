type MiniBarsProps = {
  data: { label: string; value: number }[]
  max: number
  /** Tailwind gradient classes for the bar fill. */
  tone?: string
  height?: number
}

/** Compact bar chart built from divs — enough for dashboards, no chart lib. */
export function MiniBars({
  data,
  max,
  tone = 'bg-gradient-to-t from-accent/50 to-accent',
  height = 132,
}: MiniBarsProps) {
  // The columns must stretch to the chart's fixed height, otherwise the inner
  // `flex-1` track has no definite height and each bar's `%` height resolves
  // against 0 — the chart renders completely empty.
  const ceiling = Math.max(1, max)
  return (
    <div className="flex items-stretch gap-2" style={{ height }}>
      {data.map((item) => (
        <div
          key={item.label}
          className="flex min-w-0 flex-1 flex-col items-center gap-2"
        >
          <div className="flex min-h-0 w-full flex-1 items-end">
            <div
              className={`w-full rounded-t ${tone} transition-[height] duration-700 ease-out`}
              style={{ height: `${Math.max(4, (item.value / ceiling) * 100)}%` }}
              title={`${item.label}: ${item.value}`}
            />
          </div>
          <span className="shrink-0 text-[10px] text-subtle">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
