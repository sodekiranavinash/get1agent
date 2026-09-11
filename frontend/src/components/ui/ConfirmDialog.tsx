import type { ReactNode } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import { Dialog } from './Dialog'
import { Button } from './Button'

type ConfirmDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: string
  confirmLabel?: string
  destructive?: boolean
  loading?: boolean
  children?: ReactNode
  onConfirm: () => void
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  destructive = false,
  loading = false,
  children,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="md"
      title={title}
      description={description}
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            variant={destructive ? 'danger' : 'primary'}
            onClick={onConfirm}
            disabled={loading}
            icon={
              loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : destructive ? (
                <AlertTriangle className="h-4 w-4" />
              ) : undefined
            }
          >
            {loading ? 'Working…' : confirmLabel}
          </Button>
        </>
      }
    >
      {children ?? (
        <p className="text-sm text-muted">
          {destructive ? 'This action cannot be undone.' : 'Continue?'}
        </p>
      )}
    </Dialog>
  )
}
