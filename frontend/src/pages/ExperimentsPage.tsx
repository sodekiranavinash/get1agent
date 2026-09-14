import { useState } from 'react'
import { motion } from 'framer-motion'
import { FlaskConical, Play, Plus } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Progress } from '../components/ui/progress'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs'
import { fadeUp, stagger } from '../lib/motion'

const models = ['Claude Sonnet 4', 'GPT-4o', 'Gemini 2.0 Pro', 'DeepSeek R1']
const datasets = ['support-faq', 'product-docs-qa', 'release-notes']

const experiments = [
  {
    name: 'prompt-v3 vs v2',
    model: 'Claude Sonnet 4',
    dataset: 'support-faq',
    score: 86,
    status: 'complete' as const,
  },
  {
    name: 'reasoning-high sweep',
    model: 'GPT-4o',
    dataset: 'product-docs-qa',
    score: 78,
    status: 'complete' as const,
  },
  {
    name: 'rerank on/off',
    model: 'Claude Sonnet 4',
    dataset: 'release-notes',
    score: 91,
    status: 'running' as const,
  },
]

const filters = ['all', 'complete', 'running'] as const
type Filter = (typeof filters)[number]

export function ExperimentsPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const visible = experiments.filter((run) =>
    filter === 'all' ? true : run.status === filter,
  )

  return (
    <PageShell>
      <PageHeader
        title="Experiments"
        description="Try prompts and models side by side, then compare results against a dataset."
        badge="Evaluate"
        action={{ label: 'New experiment', icon: <Plus className="size-3.5" /> }}
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
        <motion.div variants={fadeUp}>
          <Card padding="none" className="overflow-hidden">
            <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
              <div className="flex items-center gap-2">
                <FlaskConical className="size-4 text-accent" strokeWidth={1.75} />
                <span className="text-[13px] font-semibold text-foreground">
                  Playground
                </span>
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                <Select defaultValue={models[0]}>
                  <SelectTrigger className="h-8 w-[180px]">
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
                <Select defaultValue={datasets[0]}>
                  <SelectTrigger className="h-8 w-[170px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {datasets.map((dataset) => (
                      <SelectItem key={dataset} value={dataset}>
                        {dataset}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button icon={<Play className="size-3.5" />}>Run</Button>
              </div>
            </div>

            <div className="grid gap-0 lg:grid-cols-2">
              <div className="border-b border-border p-4 lg:border-r lg:border-b-0">
                <label className="mb-1.5 block text-xs font-medium text-muted">
                  Prompt
                </label>
                <textarea
                  defaultValue={
                    'You are a support assistant. Answer using only the provided knowledge base context.\n\nQuestion: {{input}}'
                  }
                  rows={9}
                  className="field resize-none font-mono text-xs leading-relaxed"
                />
              </div>
              <div className="p-4">
                <label className="mb-1.5 block text-xs font-medium text-muted">
                  Output
                </label>
                <div className="h-[210px] overflow-auto rounded-md border border-border bg-canvas p-3 text-[13px] leading-relaxed text-foreground scrollbar-thin">
                  <p className="text-muted">
                    Run the playground to see the model output and score here.
                  </p>
                </div>
              </div>
            </div>
          </Card>
        </motion.div>

        <motion.div variants={fadeUp}>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h2 className="text-xs font-semibold text-foreground">
              Recent experiments
            </h2>
            <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
              <TabsList>
                <TabsTrigger value="all">All</TabsTrigger>
                <TabsTrigger value="complete">Complete</TabsTrigger>
                <TabsTrigger value="running">Running</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          <Card padding="none" className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="border-b border-border bg-raised/40">
                    {['Experiment', 'Model', 'Dataset', 'Score', 'Status'].map(
                      (header) => (
                        <th
                          key={header}
                          className="px-4 py-2.5 text-[11px] font-semibold text-muted"
                        >
                          {header}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {visible.map((run) => (
                    <tr
                      key={run.name}
                      className="transition-colors hover:bg-raised/40"
                    >
                      <td className="px-4 py-2.5 text-[13px] font-medium text-foreground">
                        {run.name}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted">{run.model}</td>
                      <td className="px-4 py-2.5 font-mono text-xs text-muted">
                        {run.dataset}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <Progress value={run.score} className="w-24" />
                          <span className="text-xs tabular-nums text-foreground">
                            {run.score}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge
                          variant={run.status === 'running' ? 'accent' : 'success'}
                          dot
                        >
                          {run.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </motion.div>
      </motion.div>
    </PageShell>
  )
}
