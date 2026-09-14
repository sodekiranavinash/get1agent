import { motion } from 'framer-motion'
import { ClipboardCheck, Database, Gauge, Plus, Target } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Progress } from '../components/ui/progress'
import { StatCard } from '../components/ui/StatCard'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { fadeUp, stagger } from '../lib/motion'

const kpis = [
  {
    label: 'Average score',
    value: '84%',
    change: '+4% vs last week',
    trend: 'up' as const,
    icon: Target,
    spark: [72, 75, 78, 79, 82, 83, 84],
  },
  {
    label: 'Pass rate',
    value: '91%',
    change: '+2% vs last week',
    trend: 'up' as const,
    icon: ClipboardCheck,
    iconColor: 'text-info',
    spark: [85, 86, 88, 89, 90, 90, 91],
  },
  {
    label: 'Datasets',
    value: '6',
    change: '2 updated',
    trend: 'neutral' as const,
    icon: Database,
    iconColor: 'text-success',
    spark: [3, 4, 4, 5, 5, 6, 6],
  },
  {
    label: 'Evaluators',
    value: '9',
    change: '3 custom',
    trend: 'neutral' as const,
    icon: Gauge,
    iconColor: 'text-warning',
    spark: [5, 6, 6, 7, 8, 8, 9],
  },
]

const runs = [
  {
    name: 'support-faq · nightly',
    dataset: 'support-faq',
    evaluator: 'answer-correctness',
    score: 88,
    status: 'passed' as const,
  },
  {
    name: 'docs-qa · release-42',
    dataset: 'product-docs-qa',
    evaluator: 'groundedness',
    score: 76,
    status: 'passed' as const,
  },
  {
    name: 'release-notes · weekly',
    dataset: 'release-notes',
    evaluator: 'relevance',
    score: 62,
    status: 'failed' as const,
  },
]

const datasets = [
  { name: 'support-faq', rows: 320, updated: '2h ago' },
  { name: 'product-docs-qa', rows: 148, updated: 'Yesterday' },
  { name: 'release-notes', rows: 64, updated: '3 days ago' },
]

const evaluators = [
  { name: 'answer-correctness', type: 'LLM judge' },
  { name: 'groundedness', type: 'LLM judge' },
  { name: 'relevance', type: 'Heuristic' },
  { name: 'exact-match', type: 'Rule' },
]

export function EvaluationsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Evaluations"
        description="Score agent outputs against datasets with reusable evaluators."
        badge="Evaluate"
        action={{ label: 'New evaluation', icon: <Plus className="size-3.5" /> }}
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {kpis.map((kpi) => (
            <motion.div key={kpi.label} variants={fadeUp}>
              <StatCard {...kpi} />
            </motion.div>
          ))}
        </div>

        <motion.div variants={fadeUp}>
          <Tabs defaultValue="runs">
            <TabsList>
              <TabsTrigger value="runs">Runs</TabsTrigger>
              <TabsTrigger value="datasets">Datasets</TabsTrigger>
              <TabsTrigger value="evaluators">Evaluators</TabsTrigger>
            </TabsList>

            <TabsContent value="runs">
              <Card padding="none" className="overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[720px] text-left">
                    <thead>
                      <tr className="border-b border-border bg-raised/40">
                        {['Evaluation', 'Dataset', 'Evaluator', 'Score', 'Status'].map(
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
                      {runs.map((run) => (
                        <tr
                          key={run.name}
                          className="transition-colors hover:bg-raised/40"
                        >
                          <td className="px-4 py-2.5 text-[13px] font-medium text-foreground">
                            {run.name}
                          </td>
                          <td className="px-4 py-2.5 font-mono text-xs text-muted">
                            {run.dataset}
                          </td>
                          <td className="px-4 py-2.5 text-xs text-muted">
                            {run.evaluator}
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
                              variant={run.status === 'passed' ? 'success' : 'warning'}
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
            </TabsContent>

            <TabsContent value="datasets">
              <Card padding="none" className="overflow-hidden">
                <div className="divide-y divide-border">
                  {datasets.map((dataset) => (
                    <div
                      key={dataset.name}
                      className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-raised/40"
                    >
                      <span className="flex size-7 items-center justify-center rounded-md border border-border bg-raised text-info">
                        <Database className="size-3.5" strokeWidth={1.75} />
                      </span>
                      <span className="min-w-0 flex-1 font-mono text-[13px] text-foreground">
                        {dataset.name}
                      </span>
                      <span className="text-xs text-muted">{dataset.rows} rows</span>
                      <span className="w-24 text-right text-xs text-subtle">
                        {dataset.updated}
                      </span>
                      <Button variant="outline" size="sm">
                        Open
                      </Button>
                    </div>
                  ))}
                </div>
              </Card>
            </TabsContent>

            <TabsContent value="evaluators">
              <Card padding="none" className="overflow-hidden">
                <div className="divide-y divide-border">
                  {evaluators.map((evaluator) => (
                    <div
                      key={evaluator.name}
                      className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-raised/40"
                    >
                      <span className="flex size-7 items-center justify-center rounded-md border border-border bg-raised text-accent">
                        <Gauge className="size-3.5" strokeWidth={1.75} />
                      </span>
                      <span className="min-w-0 flex-1 text-[13px] font-medium text-foreground">
                        {evaluator.name}
                      </span>
                      <Badge>{evaluator.type}</Badge>
                    </div>
                  ))}
                </div>
              </Card>
            </TabsContent>
          </Tabs>
        </motion.div>
      </motion.div>
    </PageShell>
  )
}
