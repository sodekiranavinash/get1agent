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
}

export function FileDropzone({
  onFiles,
  onRejected,
  disabled = false,
  remaining,
  compact = false,
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
      className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border border-dashed text-center transition-colors ${
        compact ? 'px-4 py-6' : 'px-6 py-10'
      } ${
        isDragActive
          ? 'border-accent bg-accent-soft/40'
          : 'border-border-strong bg-raised/20 hover:border-accent/40 hover:bg-raised/40'
      } ${disabled || remaining <= 0 ? 'pointer-events-none opacity-60' : ''}`}
    >
      <input {...getInputProps()} />
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <UploadCloud className="h-5 w-5" strokeWidth={1.5} />
      </div>
      <p className="mt-3 text-sm font-medium text-foreground">
        {isDragActive ? 'Drop files to add them' : 'Drag & drop files, or click to browse'}
      </p>
      <p className="mt-1 text-xs text-muted">
        {remaining <= 0
          ? `Limit of ${MAX_FILES_PER_KB} files reached`
          : `PDF, DOCX, TXT, MD, CSV, XLSX · up to ${formatBytes(MAX_FILE_BYTES)} each · ${remaining} slot${remaining === 1 ? '' : 's'} left`}
      </p>
    </div>
  )
}
