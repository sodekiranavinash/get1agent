import { Toaster as Sonner, type ToasterProps } from 'sonner'
import { useTheme } from '@/theme/ThemeProvider'

/** App-wide toast surface, themed by our light/dark tokens. */
export function Toaster(props: ToasterProps) {
  const { theme } = useTheme()

  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            'group toast rounded-lg border border-border bg-surface text-foreground shadow-panel text-[13px]',
          description: 'text-muted text-xs',
          actionButton: 'bg-accent text-white rounded-md',
          cancelButton: 'bg-raised text-muted rounded-md',
        },
      }}
      {...props}
    />
  )
}
