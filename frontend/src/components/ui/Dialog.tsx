import type { ReactNode } from 'react'
import * as RadixDialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

type DialogSize = 'md' | 'lg' | 'xl'

type DialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  size?: DialogSize
  children: ReactNode
  footer?: ReactNode
}

const sizeStyles: Record<DialogSize, string> = {
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  size = 'lg',
  children,
  footer,
}: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-black/65 backdrop-blur-sm" />
        <RadixDialog.Content
          className={`dialog-content fixed left-1/2 top-1/2 z-50 flex max-h-[90vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-2xl border border-border-strong bg-surface shadow-panel focus:outline-none ${sizeStyles[size]}`}
        >
          <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
            <div className="min-w-0">
              <RadixDialog.Title className="text-lg font-semibold tracking-tight text-foreground">
                {title}
              </RadixDialog.Title>
              {description ? (
                <RadixDialog.Description className="mt-1 text-sm leading-relaxed text-muted">
                  {description}
                </RadixDialog.Description>
              ) : null}
            </div>
            <RadixDialog.Close
              className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
              aria-label="Close dialog"
            >
              <X className="h-4 w-4" />
            </RadixDialog.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5 scrollbar-thin">
            {children}
          </div>

          {footer ? (
            <div className="flex items-center justify-end gap-3 border-t border-border bg-raised/40 px-6 py-4">
              {footer}
            </div>
          ) : null}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}
