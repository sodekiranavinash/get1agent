import { motion } from 'framer-motion'
import { Bot, FileStack, Plus, Sparkles, Wrench } from 'lucide-react'
import type { ReactNode } from 'react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { fadeUp, stagger } from '../lib/motion'

const models = ['Claude Sonnet 4', 'GPT-4o', 'Gemini 2.0 Pro', 'DeepSeek R1']
const reasoningLevels = ['Low', 'Medium', 'High']
const defaultTools = [
  { name: 'Web Search', icon: Sparkles },
  { name: 'Code Interpreter', icon: Wrench },
]

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-xs font-medium text-muted">{label}</label>
      {children}
    </div>
  )
}

export function AgentBuilderPage() {
  return (
    <PageShell>
      <PageHeader
        title="Agent builder"
        description="Design custom agents with prompts, models, reasoning effort, tools, and knowledge bases."
        badge="Build"
        action={{ label: 'Save agent', icon: <Plus className="size-3.5" /> }}
      />

      <motion.div
        variants={stagger}
        initial="hidden"
        animate="show"
        className="grid gap-3 lg:grid-cols-[1fr_320px]"
      >
        <motion.div variants={fadeUp}>
          <Card padding="lg" className="h-full">
            <div className="mb-4 flex items-center gap-3">
              <div className="flex size-9 items-center justify-center rounded-md border border-border bg-raised text-accent">
                <Bot className="size-4" strokeWidth={1.75} />
              </div>
              <div>
                <h2 className="text-[13px] font-semibold text-foreground">
                  Agent configuration
                </h2>
                <p className="text-xs text-muted">
                  Define behavior, model, and capabilities
                </p>
              </div>
            </div>

            <div className="space-y-4">
              <Field label="Agent name">
                <div className="field flex h-9 items-center text-subtle">
                  Research Assistant
                </div>
              </Field>

              <Field label="System prompt">
                <div className="field h-28 p-3 font-mono text-xs text-subtle">
                  You are a careful research assistant…
                </div>
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Model">
                  <Select defaultValue={models[0]}>
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {models.map((model) => (
                        <SelectItem key={model} value={model}>
                          {model}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field label="Reasoning effort">
                  <Select defaultValue="Medium">
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {reasoningLevels.map((level) => (
                        <SelectItem key={level} value={level}>
                          {level}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              </div>
            </div>
          </Card>
        </motion.div>

        <div className="space-y-3">
          <motion.div variants={fadeUp}>
            <Card padding="none" className="overflow-hidden">
              <div className="border-b border-border px-4 py-2.5">
                <h3 className="text-[13px] font-semibold text-foreground">
                  Knowledge bases
                </h3>
                <p className="mt-0.5 text-xs text-muted">Ready collections for RAG</p>
              </div>
              <div className="divide-y divide-border">
                <div className="flex items-center gap-2.5 px-4 py-2.5">
                  <FileStack className="size-3.5 shrink-0 text-success" strokeWidth={1.75} />
                  <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                    Product Documentation
                  </span>
                  <Badge variant="success" dot>
                    ready
                  </Badge>
                </div>
              </div>
              <div className="p-3">
                <Button variant="outline" size="sm" className="w-full">
                  Attach knowledge base
                </Button>
              </div>
            </Card>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="overflow-hidden">
              <div className="border-b border-border px-4 py-2.5">
                <h3 className="text-[13px] font-semibold text-foreground">Default tools</h3>
                <p className="mt-0.5 text-xs text-muted">Available on every run</p>
              </div>
              <div className="divide-y divide-border">
                {defaultTools.map(({ name, icon: Icon }) => (
                  <div key={name} className="flex items-center gap-2.5 px-4 py-2.5">
                    <Icon className="size-3.5 shrink-0 text-accent" strokeWidth={1.75} />
                    <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                      {name}
                    </span>
                    <Badge variant="success" dot>
                      attached
                    </Badge>
                  </div>
                ))}
              </div>
              <div className="p-3">
                <Button variant="outline" size="sm" className="w-full">
                  Add tool
                </Button>
              </div>
            </Card>
          </motion.div>
        </div>
      </motion.div>
    </PageShell>
  )
}
