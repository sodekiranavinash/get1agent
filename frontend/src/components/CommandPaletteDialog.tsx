import {
  ArrowRight,
  CornerDownLeft,
  Moon,
  Settings,
  Sun,
} from 'lucide-react'
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from './ui/command'
import { useTheme } from '../theme/ThemeProvider'

export type PaletteDestination = { label: string; to: string }

type CommandPaletteDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  destinations: PaletteDestination[]
  onNavigate: (to: string) => void
}

/** Heavy part of the palette (cmdk) — lazy-loaded only when it is opened. */
export default function CommandPaletteDialog({
  open,
  onOpenChange,
  destinations,
  onNavigate,
}: CommandPaletteDialogProps) {
  const { theme, setTheme } = useTheme()

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Search pages, tools and actions…" />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {destinations.map((item) => (
            <CommandItem
              key={item.to}
              value={`${item.label} ${item.to}`}
              onSelect={() => onNavigate(item.to)}
            >
              <ArrowRight className="size-3.5" />
              <span className="truncate">{item.label}</span>
              <span className="ml-auto truncate font-mono text-[10px] text-subtle">
                {item.to}
              </span>
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandSeparator />
        <CommandGroup heading="Preferences">
          <CommandItem
            value="toggle theme appearance dark light"
            onSelect={() => {
              setTheme(theme === 'dark' ? 'light' : 'dark')
              onOpenChange(false)
            }}
          >
            {theme === 'dark' ? (
              <Sun className="size-3.5" />
            ) : (
              <Moon className="size-3.5" />
            )}
            Switch to {theme === 'dark' ? 'light' : 'dark'} mode
          </CommandItem>
          <CommandItem value="settings account" onSelect={() => onNavigate('/settings')}>
            <Settings className="size-3.5" />
            Settings
            <span className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] text-subtle">
              <CornerDownLeft className="size-3" /> open
            </span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
