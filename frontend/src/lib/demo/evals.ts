import { DOCS, IDS, daysAgo, hoursAgo } from './shared'

/**
 * Evaluation lab: datasets + cases (Langfuse-native), runs, per-case results and
 * the bulky S3 artifact (contexts, answer, judge reasoning).
 */

export const demoEvalDatasets = {
  datasets: [
    {
      datasetId: IDS.datasetGolden,
      name: 'rag-golden-set',
      description: 'Hand-labelled RAG questions over product-docs and support-handbook.',
      caseCount: 4,
      createdAt: daysAgo(13),
      updatedAt: daysAgo(2),
    },
    {
      datasetId: IDS.datasetSupport,
      name: 'support-faqs',
      description: 'The 5 questions the support team gets most often.',
      caseCount: 3,
      createdAt: daysAgo(7),
      updatedAt: daysAgo(4),
    },
  ],
}

const goldenCases = [
  {
    caseId: 'case_q3_rest',
    datasetId: IDS.datasetGolden,
    query: 'Which Q3 2026 changes affect the REST API?',
    expectedOutput:
      'Streaming results and the rerank flag on GET /v2/search, and the removal of POST /v1/documents in favour of the presigned upload flow.',
    expectedSources: [
      { documentId: DOCS.releaseNotes.id, page: 2 },
      { documentId: DOCS.apiGuide.id, page: 14 },
    ],
    sourceTraceId: IDS.traceResearch,
    metadata: { difficulty: 'easy' },
    createdAt: daysAgo(12),
  },
  {
    caseId: 'case_hybrid_rrf',
    datasetId: IDS.datasetGolden,
    query: 'How does hybrid search combine the semantic and lexical legs?',
    expectedOutput:
      'The two legs run in parallel and are fused with Reciprocal Rank Fusion (k=60).',
    expectedSources: [{ documentId: DOCS.architecture.id, page: 7 }],
    sourceTraceId: 'a1b2c3d4e5f60718293a4b5c6d7e8f91',
    metadata: { difficulty: 'medium' },
    createdAt: daysAgo(10),
  },
  {
    caseId: 'case_incident',
    datasetId: IDS.datasetGolden,
    query: 'What caused the August 2026 ingestion backlog?',
    expectedOutput:
      'A poison PDF blocked a batch on the extract step; the watchdog and DLQ now isolate it.',
    expectedSources: [{ documentId: DOCS.incident.id, page: null }],
    sourceTraceId: null,
    metadata: {},
    createdAt: daysAgo(9),
  },
  {
    caseId: 'case_uploads',
    datasetId: IDS.datasetGolden,
    query: 'What is the supported way to upload a document?',
    expectedOutput:
      'Request a presigned URL, PUT the bytes directly to storage, then call complete.',
    expectedSources: [{ documentId: DOCS.apiGuide.id, page: 14 }],
    sourceTraceId: null,
    metadata: { difficulty: 'easy' },
    createdAt: daysAgo(8),
  },
]

const supportCases = [
  {
    caseId: 'case_reset_password',
    datasetId: IDS.datasetSupport,
    query: 'How do I reset a managed user password?',
    expectedOutput:
      'Admin → Users → Reset password; the emailed link expires after 60 minutes.',
    expectedSources: [{ documentId: 'd0c0a1b2-1001-4001-8001-000000001001', page: null }],
    sourceTraceId: IDS.traceSupport,
    metadata: {},
    createdAt: daysAgo(7),
  },
  {
    caseId: 'case_sla',
    datasetId: IDS.datasetSupport,
    query: 'What is the SLA for a P1 incident?',
    expectedOutput: 'First response within 30 minutes, 24/7, with a named engineer.',
    expectedSources: [{ documentId: 'd0c0a1b2-1002-4002-8002-000000001002', page: 3 }],
    sourceTraceId: 'd4e5f60718293a4b5c6d7e8f9012345',
    metadata: {},
    createdAt: daysAgo(7),
  },
  {
    caseId: 'case_refund',
    datasetId: IDS.datasetSupport,
    query: 'Can a customer get a refund mid-cycle?',
    expectedOutput:
      'Prorated credits are issued for the unused period; cash refunds need finance approval.',
    expectedSources: [{ documentId: 'd0c0a1b2-1003-4003-8003-000000001003', page: null }],
    sourceTraceId: null,
    metadata: {},
    createdAt: daysAgo(6),
  },
]

export function demoEvalDatasetDetail(id: string) {
  const meta = demoEvalDatasets.datasets.find((entry) => entry.datasetId === id)
  const cases = id === IDS.datasetSupport ? supportCases : goldenCases
  return {
    dataset: {
      ...(meta ?? demoEvalDatasets.datasets[0]),
      datasetId: meta?.datasetId ?? IDS.datasetGolden,
      cases,
    },
  }
}

export const demoEvalDatasetRuns = (id: string) => ({
  runs: demoEvalRuns.runs
    .filter((run) => run.datasetId === id)
    .map((run) => ({
      id: run.runId,
      name: `${run.datasetName} · ${run.config.mode}`,
      description: '',
      createdAt: run.createdAt,
      metadata: { runId: run.runId },
    })),
})

const goldenMetrics = {
  faithfulness: 0.81,
  answer_relevance: 0.88,
  context_relevance: 0.84,
  answer_correctness: 0.76,
  context_recall: 0.72,
  context_precision: 0.8,
  hit_rate: 0.92,
  mrr: 0.83,
  faithfulness_cases: 4,
  answer_relevance_cases: 4,
}

const previousMetrics = {
  faithfulness: 0.74,
  answer_relevance: 0.81,
  context_relevance: 0.78,
  answer_correctness: 0.69,
  context_recall: 0.66,
  context_precision: 0.73,
  hit_rate: 0.85,
  mrr: 0.77,
}

const supportMetrics = {
  faithfulness: 0.9,
  answer_relevance: 0.93,
  context_relevance: 0.89,
  answer_correctness: 0.87,
  hit_rate: 1,
  mrr: 0.92,
}

const evalRun = (
  runId: string,
  datasetId: string,
  datasetName: string,
  metrics: Record<string, number>,
  createdDaysAgo: number,
  config: Record<string, unknown> = { mode: 'rag', rerank: true, task: 'rag' },
) => ({
  runId,
  datasetId,
  datasetName,
  knowledgeBaseNames: datasetId === IDS.datasetSupport ? ['support-handbook'] : ['product-docs'],
  config,
  status: 'completed',
  caseCount: datasetId === IDS.datasetSupport ? 3 : 4,
  completedCount: datasetId === IDS.datasetSupport ? 3 : 4,
  failedCount: 0,
  skippedCount: 0,
  metrics,
  error: '',
  createdAt: daysAgo(createdDaysAgo),
  updatedAt: createdDaysAgo === 1 ? hoursAgo(20) : daysAgo(createdDaysAgo),
  completedAt: createdDaysAgo === 1 ? hoursAgo(20) : daysAgo(createdDaysAgo),
})

export const demoEvalRuns = {
  runs: [
    evalRun(IDS.evalRunLatest, IDS.datasetGolden, 'rag-golden-set', goldenMetrics, 1, {
      mode: 'rag',
      rerank: true,
      task: 'rag',
    }),
    evalRun(IDS.evalRunPrevious, IDS.datasetGolden, 'rag-golden-set', previousMetrics, 8),
    evalRun('run_2026-09-27_support', IDS.datasetSupport, 'support-faqs', supportMetrics, 2, {
      mode: 'rag',
      rerank: false,
      task: 'agent',
      agentId: IDS.agentSupport,
    }),
  ],
}

function casesForRun(runId: string) {
  if (runId === 'run_2026-09-27_support') {
    return [
      {
        caseId: 'case_reset_password',
        query: 'How do I reset a managed user password?',
        status: 'ok',
        metrics: { answer_relevance: 0.94, faithfulness: 0.92, answer_correctness: 0.9 },
        error: '',
        latencyMs: 3_180,
        retrievedCount: 2,
      },
      {
        caseId: 'case_sla',
        query: 'What is the SLA for a P1 incident?',
        status: 'ok',
        metrics: { answer_relevance: 0.92, faithfulness: 0.9, answer_correctness: 0.88 },
        error: '',
        latencyMs: 2_640,
        retrievedCount: 2,
      },
      {
        caseId: 'case_refund',
        query: 'Can a customer get a refund mid-cycle?',
        status: 'ok',
        metrics: { answer_relevance: 0.93, faithfulness: 0.88, answer_correctness: 0.83 },
        error: '',
        latencyMs: 2_980,
        retrievedCount: 3,
      },
    ]
  }
  return [
    {
      caseId: 'case_q3_rest',
      query: 'Which Q3 2026 changes affect the REST API?',
      status: 'ok',
      metrics: { faithfulness: 0.9, answer_relevance: 0.92, context_relevance: 0.88, answer_correctness: 0.85 },
      error: '',
      latencyMs: 3_420,
      retrievedCount: 3,
    },
    {
      caseId: 'case_hybrid_rrf',
      query: 'How does hybrid search combine the semantic and lexical legs?',
      status: 'ok',
      metrics: { faithfulness: 0.84, answer_relevance: 0.88, context_relevance: 0.86, answer_correctness: 0.8 },
      error: '',
      latencyMs: 3_010,
      retrievedCount: 3,
    },
    {
      caseId: 'case_incident',
      query: 'What caused the August 2026 ingestion backlog?',
      status: 'ok',
      metrics: { faithfulness: 0.72, answer_relevance: 0.81, context_relevance: 0.7, answer_correctness: 0.65 },
      error: '',
      latencyMs: 2_880,
      retrievedCount: 2,
    },
    {
      caseId: 'case_uploads',
      query: 'What is the supported way to upload a document?',
      status: 'ok',
      metrics: { faithfulness: 0.78, answer_relevance: 0.9, context_relevance: 0.92, answer_correctness: 0.74 },
      error: '',
      latencyMs: 2_740,
      retrievedCount: 4,
    },
  ]
}

export function demoEvalRun(runId: string) {
  return {
    run:
      demoEvalRuns.runs.find((entry) => entry.runId === runId) ?? demoEvalRuns.runs[0],
  }
}

export function demoEvalRunCases(runId: string) {
  return { cases: casesForRun(runId) }
}

const q3Artifact = {
  query: 'Which Q3 2026 changes affect the REST API?',
  answer:
    'Two changes affect the REST API: GET /v2/search now supports streaming results and an opt-in rerank flag, and POST /v1/documents was removed in favour of the presigned upload flow.',
  expectedOutput:
    'Streaming results and the rerank flag on GET /v2/search, and the removal of POST /v1/documents in favour of the presigned upload flow.',
  status: 'ok',
  error: '',
  mode: 'rag',
  contexts: [
    {
      documentId: DOCS.releaseNotes.id,
      page: 2,
      fileName: 'release-notes-2026-q3.pdf',
      text: 'Q3 2026 · Highlights — streaming search results on GET /v2/search, an opt-in rerank flag (default off), and the removal of the legacy POST /v1/documents upload endpoint. p95 latency in the release benchmarks fell from 1.9s to 1.2s.',
    },
    {
      documentId: DOCS.apiGuide.id,
      page: 14,
      fileName: 'api-integration-guide.pdf',
      text: 'Migrate uploads: request a presigned URL with POST /v2/documents/presign, PUT the bytes to S3, then call POST /v2/documents/{id}/complete. The legacy v1 endpoint was removed in 2.14.0.',
    },
    {
      documentId: DOCS.architecture.id,
      page: 7,
      fileName: 'architecture-overview.pdf',
      text: 'Hybrid retrieval runs a semantic leg (S3 Vectors) and a lexical BM25 leg in parallel and fuses them with Reciprocal Rank Fusion (k=60). Reranking is a separate, opt-in cross-encoder pass over the fused list.',
    },
  ],
  metrics: { faithfulness: 0.9, answer_relevance: 0.92, context_relevance: 0.88, answer_correctness: 0.85 },
  judge: {
    reasoning:
      'The answer names both API-affecting changes and correctly states that reranking is opt-in and off by default. It omits the latency figure but the question did not ask for it, so that is not a faithfulness problem.',
    relevanceReasoning: 'Directly answers which changes affect the REST API.',
    contextReasoning:
      'All three retrieved passages are relevant: two cover the API surface and one covers the retrieval internals.',
    correctnessReasoning:
      'Matches the expected answer; the only gap is that it does not quote the p95 figure.',
    claims: [
      { text: 'GET /v2/search supports streaming results.', supported: true },
      { text: 'Reranking is opt-in via a flag.', supported: true },
      { text: 'POST /v1/documents was removed.', supported: true },
      { text: 'Re-indexing is required after the change.', supported: false },
    ],
    passages: [
      { index: 1, relevant: true },
      { index: 2, relevant: true },
      { index: 3, relevant: true },
    ],
  },
  retrieval: {
    chunks: [
      { chunkId: `${DOCS.releaseNotes.id}#41`, score: 0.71 },
      { chunkId: `${DOCS.apiGuide.id}#12`, score: 0.66 },
      { chunkId: `${DOCS.architecture.id}#28`, score: 0.58 },
    ],
    sources: [
      { documentId: DOCS.releaseNotes.id, page: 2 },
      { documentId: DOCS.apiGuide.id, page: 14 },
      { documentId: DOCS.architecture.id, page: 7 },
    ],
    meta: { topK: 100, fusedBy: 'rrf', k: 60, rerank: true },
  },
}

const incidentArtifact = {
  query: 'What caused the August 2026 ingestion backlog?',
  answer:
    'A single malformed PDF stalled its extract batch; the queue retried it until the watchdog and DLQ isolated it, which delayed the rest of the batch.',
  expectedOutput:
    'A poison PDF blocked a batch on the extract step; the watchdog and DLQ now isolate it.',
  status: 'ok',
  error: '',
  mode: 'rag',
  contexts: [
    {
      documentId: DOCS.incident.id,
      page: null,
      fileName: 'incident-postmortem-2026-08.md',
      text: 'Root cause: a malformed PDF caused the extract Lambda to time out, and the whole SQS batch was retried repeatedly. Fix: partial batch failures plus a move-to-DLQ after three attempts, and the watchdog now fails documents stuck in processing past 75 minutes.',
    },
  ],
  metrics: { faithfulness: 0.72, answer_relevance: 0.81, context_relevance: 0.7, answer_correctness: 0.65 },
  judge: {
    reasoning:
      'The answer captures the root cause and the isolation fix, but overstates the watchdog’s role — it fails stuck documents rather than moving them to the DLQ.',
    relevanceReasoning: 'On topic and answers the question.',
    contextReasoning: 'The single retrieved passage is relevant.',
    correctnessReasoning:
      'Broadly correct but conflates the watchdog and the DLQ, so correctness is below the others.',
    claims: [
      { text: 'A malformed PDF stalled the extract batch.', supported: true },
      { text: 'The watchdog moves poison messages to the DLQ.', supported: false },
      { text: 'Partial batch failures were introduced as a fix.', supported: true },
    ],
    passages: [{ index: 1, relevant: true }],
  },
  retrieval: {
    chunks: [{ chunkId: `${DOCS.incident.id}#3`, score: 0.63 }],
    sources: [{ documentId: DOCS.incident.id, page: null }],
    meta: { topK: 100, fusedBy: 'rrf', k: 60, rerank: false },
  },
}

const genericArtifact = (caseId: string) => ({
  query:
    caseId === 'case_uploads'
      ? 'What is the supported way to upload a document?'
      : caseId === 'case_hybrid_rrf'
        ? 'How does hybrid search combine the semantic and lexical legs?'
        : caseId === 'case_sla'
          ? 'What is the SLA for a P1 incident?'
          : 'Can a customer get a refund mid-cycle?',
  answer: 'See the retrieved contexts for the supporting passages.',
  expectedOutput: '',
  status: 'ok',
  error: '',
  mode: 'rag',
  contexts: [
    {
      documentId: DOCS.apiGuide.id,
      page: 14,
      fileName: 'api-integration-guide.pdf',
      text: 'Request a presigned URL, PUT the bytes, then complete the upload. The v1 endpoint is removed.',
    },
  ],
  metrics: { faithfulness: 0.8, answer_relevance: 0.85 },
  judge: {
    reasoning: 'Supported by the retrieved context.',
    relevanceReasoning: 'Answers the question.',
    contextReasoning: 'Relevant passage.',
    correctnessReasoning: 'Matches the expected answer.',
    claims: [{ text: 'Uploads use a presigned URL.', supported: true }],
    passages: [{ index: 1, relevant: true }],
  },
  retrieval: {
    chunks: [{ chunkId: `${DOCS.apiGuide.id}#12`, score: 0.6 }],
    sources: [{ documentId: DOCS.apiGuide.id, page: 14 }],
    meta: { topK: 100, fusedBy: 'rrf', k: 60 },
  },
})

export function demoEvalCaseArtifact(caseId: string) {
  if (caseId === 'case_q3_rest') return { artifact: q3Artifact }
  if (caseId === 'case_incident') return { artifact: incidentArtifact }
  return { artifact: genericArtifact(caseId) }
}
