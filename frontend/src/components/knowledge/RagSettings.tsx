import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Boxes, Image as ImageIcon, Lock, Scissors } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { Segmented } from '../ui/Segmented'
import {
  CHUNK_OVERLAPS,
  CHUNK_SIZES,
  DEFAULT_CHUNK_OVERLAP,
  DEFAULT_CHUNK_SIZE,
  EMBEDDING_DIM,
  IMAGE_EMBED_MODEL,
  TEXT_EMBED_MODEL,
} from '../../lib/knowledgeBases'

const MODELS = [
  {
    label: 'Text embedding model',
    icon: Boxes,
    id: TEXT_EMBED_MODEL,
    name: 'Amazon Titan Text Embeddings V2',
  },
  {
    label: 'Image embedding model',
    icon: ImageIcon,
    id: IMAGE_EMBED_MODEL,
    name: 'Amazon Titan Multimodal G1',
  },
]

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className="mb-1.5 block text-[11px] font-medium text-muted">
        {label}
      </span>
      {children}
    </div>
  )
}

function ModelValue({
  icon: Icon,
  name,
  id,
}: {
  icon: LucideIcon
  name: string
  id: string
}) {
  return (
    <div
      title={id}
      className="flex items-center gap-2.5 rounded-xl border border-border-strong bg-raised px-3 py-2"
    >
      <Icon className="h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} />
      <span className="min-w-0 flex-1 text-sm leading-tight text-foreground">
        {name}
      </span>
      <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">
        {EMBEDDING_DIM}-d
      </span>
    </div>
  )
}

export function RagSettings() {
  return (
    <Card padding="lg">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <Scissors className="h-5 w-5" strokeWidth={1.75} />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-foreground">
              Embedding &amp; chunking
            </h2>
            <p className="mt-0.5 text-xs leading-relaxed text-muted">
              Chosen per knowledge base when you create it.
            </p>
          </div>
        </div>
        <Badge variant="default">
          <Lock className="h-3 w-3" />
          Per knowledge base
        </Badge>
      </div>

      <div className="mt-5 space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {MODELS.map((model) => (
            <Field key={model.id} label={model.label}>
              <ModelValue icon={model.icon} name={model.name} id={model.id} />
            </Field>
          ))}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Chunk size (tokens)">
            <Segmented
              options={CHUNK_SIZES}
              value={DEFAULT_CHUNK_SIZE}
              disabled
              size="sm"
            />
          </Field>

          <Field label="Chunk overlap (tokens)">
            <Segmented
              options={CHUNK_OVERLAPS}
              value={DEFAULT_CHUNK_OVERLAP}
              disabled
              size="sm"
            />
          </Field>
        </div>
      </div>

      <p className="mt-4 border-t border-border pt-3 text-[11px] text-subtle">
        Set chunk size and overlap in the create dialog. They are fixed once a
        knowledge base has documents.
      </p>
    </Card>
  )
}
