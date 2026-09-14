import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../../theme/ThemeProvider'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '../ui/tooltip'

/** Single icon button that flips between light and dark mode. */
export function ThemeSwitch() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'
  const label = isDark ? 'Switch to light mode' : 'Switch to dark mode'

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={label}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-transparent text-muted transition-colors hover:border-border hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
        >
          {isDark ? (
            <Sun className="size-5" strokeWidth={1.75} />
          ) : (
            <Moon className="size-5" strokeWidth={1.75} />
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}
