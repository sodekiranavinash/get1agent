import { useState } from 'react'
import { motion } from 'framer-motion'
import { Plus } from 'lucide-react'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { useApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import { invalidateQuery } from '../lib/query'
import type { KnowledgeBaseList } from '../lib/knowledgeBases'
import { EVALS_QUERY_KEY, datasetQueryKey, datasetRunsQueryKey, type EvalDataset, type EvalRun } from '../lib/evals'
import { CompareTab } from '../components/evals/CompareTab'
import { DatasetsTab } from '../components/evals/DatasetsTab'
import { DatasetDetailDialog } from '../components/evals/DatasetDetailDialog'
import { RunsTab } from '../components/evals/RunsTab'
import { RunDetailDialog } from '../components/evals/RunDetailDialog'
import { AddCasesDialog, NewDatasetDialog, NewRunDialog } from '../components/evals/EvalDialogs'
import { fadeUp, stagger } from '../lib/motion'

type EvalsData = {
  datasets: EvalDataset[]
  runs: EvalRun[]
  kbs: KnowledgeBaseList['knowledgeBases']
  agents: { agentId: string; name: string }[]
}

export function EvaluationsPage() {
  const api = useApiClient()
  const { data, isPending, refetch } = usePageQuery<EvalsData>(EVALS_QUERY_KEY, async () => {
    const [datasets, runs, kbs, agents] = await Promise.all([
      api.get<{ datasets: EvalDataset[] }>('/v1/evals/datasets'),
      api.get<{ runs: EvalRun[] }>('/v1/evals/runs'),
      api.get<KnowledgeBaseList>('/v1/knowledge-bases'),
      api.get<{ agents: { id: string; name: string }[] }>('/v1/agents'),
    ])
    return {
      datasets: datasets.datasets,
      runs: runs.runs,
      kbs: kbs.knowledgeBases,
      agents: agents.agents.map((agent) => ({ agentId: agent.id, name: agent.name })),
    }
  })

  const [tab, setTab] = useState('datasets')
  const [newDatasetOpen, setNewDatasetOpen] = useState(false)
  const [addCasesDataset, setAddCasesDataset] = useState<EvalDataset | null>(null)
  const [runDialogOpen, setRunDialogOpen] = useState(false)
  const [runDatasetId, setRunDatasetId] = useState<string | undefined>(undefined)
  const [openRunId, setOpenRunId] = useState<string | null>(null)
  const [detailDataset, setDetailDataset] = useState<EvalDataset | null>(null)

  function refresh() {
    invalidateQuery(EVALS_QUERY_KEY)
    if (detailDataset) {
      invalidateQuery(datasetQueryKey(detailDataset.datasetId))
      invalidateQuery(datasetRunsQueryKey(detailDataset.datasetId))
    }
    refetch()
  }

  if (isPending) return <EvaluationsSkeleton />

  const datasets = data?.datasets ?? []
  const runs = data?.runs ?? []
  const kbs = data?.kbs ?? []
  const agents = data?.agents ?? []

  const action =
    tab === 'datasets'
      ? { label: 'New dataset', icon: <Plus className="size-3.5" />, onClick: () => setNewDatasetOpen(true) }
      : tab === 'runs'
        ? {
            label: 'New evaluation',
            icon: <Plus className="size-3.5" />,
            onClick: () => {
              setRunDatasetId(datasets[0]?.datasetId)
              setRunDialogOpen(true)
            },
          }
        : undefined

  return (
    <PageShell>
      <PageHeader
        title="Evaluations"
        description="Run RAG evaluations against golden datasets and compare runs."
        badge="Evaluate"
        badgeVariant="info"
        action={action}
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
        <motion.div variants={fadeUp}>
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="datasets">Datasets</TabsTrigger>
              <TabsTrigger value="runs">Runs</TabsTrigger>
              <TabsTrigger value="compare">Compare</TabsTrigger>
            </TabsList>

            <TabsContent value="datasets">
              <DatasetsTab
                datasets={datasets}
                onRefresh={refresh}
                onOpen={(dataset) => {
                  invalidateQuery(datasetQueryKey(dataset.datasetId))
                  invalidateQuery(datasetRunsQueryKey(dataset.datasetId))
                  setDetailDataset(dataset)
                }}
                onAddCases={(dataset) => setAddCasesDataset(dataset)}
                onRun={(dataset) => {
                  setRunDatasetId(dataset.datasetId)
                  setRunDialogOpen(true)
                }}
              />
            </TabsContent>

            <TabsContent value="runs">
              <RunsTab runs={runs} onOpen={setOpenRunId} onRefresh={refresh} />
            </TabsContent>

            <TabsContent value="compare">
              <CompareTab runs={runs} />
            </TabsContent>
          </Tabs>
        </motion.div>
      </motion.div>

      <NewDatasetDialog open={newDatasetOpen} onOpenChange={setNewDatasetOpen} onCreated={refresh} />
      <AddCasesDialog
        dataset={addCasesDataset}
        onOpenChange={(open) => {
          if (!open) setAddCasesDataset(null)
        }}
        onAdded={refresh}
      />
      <NewRunDialog
        key={runDatasetId ?? 'none'}
        open={runDialogOpen}
        datasets={datasets}
        initialDatasetId={runDatasetId}
        knowledgeBases={kbs}
        agents={agents}
        onOpenChange={setRunDialogOpen}
        onStarted={(run) => {
          refresh()
          setTab('runs')
          setOpenRunId(run.runId)
        }}
      />
      <RunDetailDialog
        key={openRunId ?? 'none'}
        runId={openRunId}
        onOpenChange={(open) => !open && setOpenRunId(null)}
      />
      <DatasetDetailDialog
        key={detailDataset?.datasetId ?? 'none'}
        dataset={detailDataset}
        onOpenChange={(open) => !open && setDetailDataset(null)}
        onRun={(dataset) => {
          setDetailDataset(null)
          setRunDatasetId(dataset.datasetId)
          setRunDialogOpen(true)
        }}
        onAddCases={(dataset) => {
          setDetailDataset(null)
          setAddCasesDataset(dataset)
        }}
      />
    </PageShell>
  )
}

function EvaluationsSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-72" />
      </div>
      <Skeleton className="mb-3 h-8 w-64" />
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-14 w-full" />
        ))}
      </div>
    </PageShell>
  )
}
