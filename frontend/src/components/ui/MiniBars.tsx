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
  return (
    <div className="flex items-end gap-2" style={{ height }}>
      {data.map((item) => (
        <div key={item.label} className="flex flex-1 flex-col items-center gap-2">
          <div className="flex w-full flex-1 items-end">
            <div
              className={`w-full rounded-t ${tone} transition-[height] duration-700 ease-out`}
              style={{ height: `${Math.max(4, (item.value / max) * 100)}%` }}
              title={`${item.label}: ${item.value}`}
            />
          </div>
          <span className="text-[10px] text-subtle">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
