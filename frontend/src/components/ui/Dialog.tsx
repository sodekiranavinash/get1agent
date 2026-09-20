import type { ReactNode } from 'react'
import * as RadixDialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'

type DialogSize = 'md' | 'lg' | 'xl' | '2xl'

type DialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  icon?: ReactNode
  size?: DialogSize
  banner?: ReactNode
  contentClassName?: string
  children: ReactNode
  footer?: ReactNode
}

const sizeStyles: Record<DialogSize, string> = {
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl',
  '2xl': 'max-w-6xl',
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  icon,
  size = 'lg',
  banner,
  contentClassName = '',
  children,
  footer,
}: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="dialog-overlay fixed inset-0 z-50 bg-black/60 backdrop-blur-[2px]" />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <RadixDialog.Content
            className={`dialog-content relative flex max-h-[90vh] w-full flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-panel focus:outline-none ${sizeStyles[size]} ${contentClassName}`}
          >
          <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-3.5">
            <div className="flex min-w-0 items-start gap-3">
              {icon ? <span className="mt-0.5 shrink-0">{icon}</span> : null}
              <div className="min-w-0">
                <RadixDialog.Title className="text-sm font-semibold tracking-tight text-foreground">
                  {title}
                </RadixDialog.Title>
                {description ? (
                  <RadixDialog.Description className="mt-0.5 text-xs leading-relaxed text-muted">
                    {description}
                  </RadixDialog.Description>
                ) : null}
              </div>
            </div>
            <RadixDialog.Close
              className="-mr-1 rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
              aria-label="Close dialog"
            >
              <X className="h-4 w-4" />
            </RadixDialog.Close>
          </div>

          {banner ? (
            <div className="border-b border-border px-5 py-3">{banner}</div>
          ) : null}

          <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
            {children}
          </div>

          {footer ? (
            <div className="flex items-center justify-end gap-2 border-t border-border bg-raised/40 px-5 py-3">
              {footer}
            </div>
          ) : null}
          </RadixDialog.Content>
        </div>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}
