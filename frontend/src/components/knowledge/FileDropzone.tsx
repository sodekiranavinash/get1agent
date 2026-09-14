import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { UploadCloud } from 'lucide-react'
import {
  ACCEPTED_MIME,
  MAX_FILES_PER_KB,
  MAX_FILE_BYTES,
  formatBytes,
} from '../../lib/knowledgeBases'

type FileDropzoneProps = {
  onFiles: (files: File[]) => void
  onRejected?: (message: string) => void
  disabled?: boolean
  remaining: number
  compact?: boolean
  className?: string
}

export function FileDropzone({
  onFiles,
  onRejected,
  disabled = false,
  remaining,
  compact = false,
  className = '',
}: FileDropzoneProps) {
  const onDrop = useCallback(
    (accepted: File[], rejections: { file: File }[]) => {
      if (rejections.length > 0) {
        onRejected?.(`${rejections[0].file.name} is not an allowed file type`)
      }
      if (accepted.length > 0) onFiles(accepted)
    },
    [onFiles, onRejected],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_MIME,
    multiple: true,
    disabled: disabled || remaining <= 0,
  })

  return (
    <div
      {...getRootProps()}
      className={`flex cursor-pointer items-center justify-center gap-3 rounded-lg border border-dashed text-center transition-colors ${
        compact ? 'px-4 py-3' : 'flex-col px-6 py-8'
      } ${
        isDragActive
          ? 'border-accent bg-accent-soft'
          : 'border-border-strong bg-raised/20 hover:border-accent/50 hover:bg-raised/40'
      } ${disabled || remaining <= 0 ? 'pointer-events-none opacity-60' : ''} ${className}`}
    >
      <input {...getInputProps()} />
      <div
        className={`flex shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent ${
          compact ? 'h-8 w-8' : 'h-10 w-10'
        }`}
      >
        <UploadCloud className={compact ? 'h-4 w-4' : 'h-5 w-5'} strokeWidth={1.5} />
      </div>
      <div className={compact ? 'text-left' : ''}>
        <p className="text-[13px] font-medium text-foreground">
          {isDragActive ? 'Drop files to add them' : 'Drag & drop files, or click to browse'}
        </p>
        <p className="mt-0.5 text-xs text-muted">
          {remaining <= 0
            ? `Limit of ${MAX_FILES_PER_KB} files reached`
            : `PDF, DOCX, TXT, MD, CSV, XLSX · up to ${formatBytes(MAX_FILE_BYTES)} each · ${remaining} slot${remaining === 1 ? '' : 's'} left`}
        </p>
      </div>
    </div>
  )
}
