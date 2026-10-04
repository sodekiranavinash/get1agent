import { DOCS, IDS, daysAgo, hoursAgo, minutesAgo } from './shared'

/**
 * Knowledge bases, their documents, tags and the ingestion event timeline.
 * `/v1/knowledge-bases`, `/v1/knowledge-bases/{id}`, `/v1/knowledge-bases/tags`
 * and `/v1/knowledge-bases/events`.
 */

const productDocs = {
  id: IDS.kbProductDocs,
  name: 'product-docs',
  description: 'Product documentation, release notes and integration guides.',
  status: 'ready',
  fileCount: 12,
    embedModel: 'amazon.titan-embed-text-v2:0',
    imageEmbedModel: 'amazon.titan-embed-image-v1',
  embeddingDim: 1024,
  chunkSize: 512,
  chunkOverlap: 64,
  createdAt: daysAgo(88),
  updatedAt: hoursAgo(5),
}

const supportHandbook = {
  id: IDS.kbSupportHandbook,
  name: 'support-handbook',
  description: 'Support playbooks, escalation policies and customer FAQs.',
  status: 'ready',
  fileCount: 5,
    embedModel: 'amazon.titan-embed-text-v2:0',
    imageEmbedModel: 'amazon.titan-embed-image-v1',
  embeddingDim: 1024,
  chunkSize: 384,
  chunkOverlap: 48,
  createdAt: daysAgo(61),
  updatedAt: daysAgo(3),
}

const researchPapers = {
  id: IDS.kbResearchPapers,
  name: 'research-papers',
  description: 'Retrieval and evaluation papers the team is reading.',
  status: 'ready',
  fileCount: 7,
    embedModel: 'amazon.titan-embed-text-v2:0',
    imageEmbedModel: 'amazon.titan-embed-image-v1',
  embeddingDim: 1024,
  chunkSize: 512,
  chunkOverlap: 64,
  createdAt: daysAgo(34),
  updatedAt: daysAgo(9),
}

export const demoKnowledgeBases = [productDocs, supportHandbook, researchPapers]

/**
 * Files that actually exist under `public/demo/` so the citation previews in
 * chat render a real document page instead of a broken S3 URL. Documents with
 * no asset fall back to a document icon in the source carousel.
 */
const DEMO_ASSET: Record<string, string> = {
  'release-notes-2026-q3.pdf': '/demo/release-notes-2026-q3.pdf',
  'architecture-overview.pdf': '/demo/architecture-overview.pdf',
  'api-integration-guide.pdf': '/demo/api-integration-guide.pdf',
  'incident-postmortem-2026-08.md': '/demo/incident-postmortem-2026-08.md',
  'support-playbook.md': '/demo/support-playbook.md',
  'escalation-policy.pdf': '/demo/escalation-policy.pdf',
  'billing-faqs.pdf': '/demo/billing-faqs.pdf',
}

const doc = (
  id: string,
  fileName: string,
  contentType: string,
  sizeBytes: number,
  status: string,
  chunkCount: number,
  imageCount: number,
  tags: { name: string; description: string }[],
  createdDaysAgo: number,
  updatedHoursAgo: number,
  source = 'upload',
) => ({
  id,
  knowledgeBaseId: IDS.kbProductDocs,
  fileName,
  contentType,
  sizeBytes,
  source,
  status,
  chunkCount,
  imageCount,
  tags,
  createdAt: daysAgo(createdDaysAgo),
  updatedAt: hoursAgo(updatedHoursAgo),
  downloadUrl: DEMO_ASSET[fileName] ?? null,
})

const productDocuments = [
  doc(
    DOCS.releaseNotes.id,
    DOCS.releaseNotes.fileName,
    'application/pdf',
    1_842_311,
    'ready',
    96,
    4,
    [
      { name: 'release-notes', description: 'Per-release changelogs' },
      { name: 'q3-2026', description: 'Q3 2026 cycle' },
    ],
    12,
    5,
  ),
  doc(
    DOCS.architecture.id,
    DOCS.architecture.fileName,
    'application/pdf',
    3_204_882,
    'ready',
    142,
    11,
    [
      { name: 'architecture', description: 'System design references' },
      { name: 'engineering', description: 'Internal engineering docs' },
    ],
    44,
    72,
  ),
  doc(
    DOCS.apiGuide.id,
    DOCS.apiGuide.fileName,
    'application/pdf',
    986_442,
    'ready',
    61,
    2,
    [{ name: 'api', description: 'API + SDK integration' }],
    30,
    120,
  ),
  doc(
    DOCS.incident.id,
    DOCS.incident.fileName,
    'text/markdown',
    38_120,
    'ready',
    14,
    0,
    [
      { name: 'postmortem', description: 'Incident write-ups' },
      { name: 'engineering', description: 'Internal engineering docs' },
    ],
    18,
    12,
  ),
  doc(
    'd0c0a1b2-0005-4005-8005-000000000005',
    'pricing-faq.pdf',
    'application/pdf',
    421_009,
    'ready',
    22,
    1,
    [{ name: 'pricing', description: 'Plans and billing' }],
    27,
    240,
  ),
  doc(
    'd0c0a1b2-0006-4006-8006-000000000006',
    'security-overview.pdf',
    'application/pdf',
    1_120_774,
    'ready',
    58,
    3,
    [{ name: 'security', description: 'Compliance + trust' }],
    52,
    300,
  ),
  doc(
    'd0c0a1b2-0007-4007-8007-000000000007',
    'onboarding-checklist.docx',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    88_201,
    'ready',
    9,
    0,
    [{ name: 'onboarding', description: 'Customer onboarding' }],
    20,
    96,
  ),
  // Two documents still in flight so the Activity panel has live work to show.
  doc(
    'd0c0a1b2-0008-4008-8008-000000000008',
    'roadmap-2027.pdf',
    'application/pdf',
    2_442_118,
    'processing',
    0,
    0,
    [{ name: 'roadmap', description: 'Forward-looking plans' }],
    0,
    0.02,
  ),
  doc(
    'd0c0a1b2-0009-4009-8009-000000000009',
    'sdk-migration-guide.pdf',
    'application/pdf',
    655_210,
    'failed',
    0,
    0,
    [{ name: 'api', description: 'API + SDK integration' }],
    1,
    26,
  ),
]

export const demoKnowledgeBaseDetail = (id: string) => {
  const kb = demoKnowledgeBases.find((entry) => entry.id === id) ?? productDocs
  if (kb.id === IDS.kbSupportHandbook) {
    return {
      knowledgeBase: kb,
      documents: [
        {
          ...doc(
            'd0c0a1b2-1001-4001-8001-000000001001',
            'support-playbook.md',
            'text/markdown',
            61_002,
            'ready',
            18,
            0,
            [{ name: 'support', description: 'Customer support' }],
            40,
            60,
          ),
          knowledgeBaseId: IDS.kbSupportHandbook,
        },
        {
          ...doc(
            'd0c0a1b2-1002-4002-8002-000000001002',
            'escalation-policy.pdf',
            'application/pdf',
            220_450,
            'ready',
            31,
            1,
            [{ name: 'support', description: 'Customer support' }],
            38,
            90,
          ),
          knowledgeBaseId: IDS.kbSupportHandbook,
        },
        {
          ...doc(
            'd0c0a1b2-1003-4003-8003-000000001003',
            'billing-faqs.pdf',
            'application/pdf',
            180_220,
            'ready',
            24,
            0,
            [
              { name: 'support', description: 'Customer support' },
              { name: 'pricing', description: 'Plans and billing' },
            ],
            25,
            200,
          ),
          knowledgeBaseId: IDS.kbSupportHandbook,
        },
      ],
    }
  }
  if (kb.id === IDS.kbResearchPapers) {
    return {
      knowledgeBase: kb,
      documents: [
        {
          ...doc(
            'd0c0a1b2-2001-4001-8001-000000002001',
            'hybrid-retrieval.pdf',
            'application/pdf',
            1_402_882,
            'ready',
            74,
            6,
            [{ name: 'retrieval', description: 'Search + ranking' }],
            30,
            320,
          ),
          knowledgeBaseId: IDS.kbResearchPapers,
        },
        {
          ...doc(
            'd0c0a1b2-2002-4002-8002-000000002002',
            'rag-evaluation-survey.pdf',
            'application/pdf',
            2_115_004,
            'ready',
            108,
            3,
            [{ name: 'evaluation', description: 'Eval methodology' }],
            22,
            280,
          ),
          knowledgeBaseId: IDS.kbResearchPapers,
        },
      ],
    }
  }
  return { knowledgeBase: productDocs, documents: productDocuments }
}

export const demoKnowledgeBaseTags = {
  tags: [
    { name: 'engineering', description: 'Internal engineering docs' },
    { name: 'api', description: 'API + SDK integration' },
    { name: 'release-notes', description: 'Per-release changelogs' },
    { name: 'support', description: 'Customer support' },
    { name: 'pricing', description: 'Plans and billing' },
    { name: 'security', description: 'Compliance + trust' },
    { name: 'architecture', description: 'System design references' },
    { name: 'evaluation', description: 'Eval methodology' },
  ],
}

/** Newest first; the Activity panel groups these by `documentId`. */
export const demoIngestionEvents = {
  events: [
    {
      id: 9042,
      documentId: 'd0c0a1b2-0008-4008-8008-000000000008',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'roadmap-2027.pdf',
      documentStatus: 'processing',
      stage: 'embedding',
      status: 'started',
      message: null,
      details: {
        chunks: 128,
        tokens: 61_440,
        chunkSize: 512,
        chunkOverlap: 64,
        model: 'amazon.titan-embed-text-v2:0',
        dimension: 1024,
      },
      createdAt: minutesAgo(2),
    },
    {
      id: 9041,
      documentId: 'd0c0a1b2-0008-4008-8008-000000000008',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'roadmap-2027.pdf',
      documentStatus: 'processing',
      stage: 'chunked',
      status: 'succeeded',
      message: 'Split into 128 chunks',
      details: {
        chunks: 128,
        tokens: 61_440,
        chunkSize: 512,
        chunkOverlap: 64,
      },
      createdAt: minutesAgo(3),
    },
    {
      id: 9040,
      documentId: 'd0c0a1b2-0008-4008-8008-000000000008',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'roadmap-2027.pdf',
      documentStatus: 'processing',
      stage: 'extracted',
      status: 'succeeded',
      message: 'Parsed 42 pages',
      details: {
        sourceBytes: 2_442_118,
        characters: 184_220,
        words: 31_540,
        pages: 42,
        images: 6,
      },
      createdAt: minutesAgo(4),
    },
    {
      id: 9039,
      documentId: 'd0c0a1b2-0008-4008-8008-000000000008',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'roadmap-2027.pdf',
      documentStatus: 'uploaded',
      stage: 'uploaded',
      status: 'succeeded',
      message: null,
      details: { sizeBytes: 2_442_118, contentType: 'application/pdf', source: 'upload' },
      createdAt: minutesAgo(5),
    },
    {
      id: 9038,
      documentId: 'd0c0a1b2-0009-4009-8009-000000000009',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'sdk-migration-guide.pdf',
      documentStatus: 'failed',
      stage: 'failed',
      status: 'failed',
      message: 'Could not parse the PDF — the file may be encrypted.',
      details: { failedStage: 'extracted' },
      createdAt: hoursAgo(26),
    },
    {
      id: 9037,
      documentId: 'd0c0a1b2-0004-4004-8004-000000000004',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'incident-postmortem-2026-08.md',
      documentStatus: 'ready',
      stage: 'indexed',
      status: 'succeeded',
      message: 'Indexed 14 chunks',
      details: {
        vectors: 14,
        textEmbeddings: 14,
        imageEmbeddings: 0,
        dimension: 1024,
        model: 'amazon.titan-embed-text-v2:0',
      },
      createdAt: hoursAgo(12),
    },
    {
      id: 9036,
      documentId: 'd0c0a1b2-0004-4004-8004-000000000004',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'incident-postmortem-2026-08.md',
      documentStatus: 'processing',
      stage: 'embedding',
      status: 'succeeded',
      message: null,
      details: {
        embeddings: 14,
        textEmbeddings: 14,
        imageEmbeddings: 0,
        dimension: 1024,
        model: 'amazon.titan-embed-text-v2:0',
      },
      createdAt: hoursAgo(12),
    },
    {
      id: 9035,
      documentId: 'd0c0a1b2-0004-4004-8004-000000000004',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'incident-postmortem-2026-08.md',
      documentStatus: 'processing',
      stage: 'chunked',
      status: 'succeeded',
      message: 'Split into 14 chunks',
      details: { chunks: 14, tokens: 6_720, chunkSize: 512, chunkOverlap: 64 },
      createdAt: hoursAgo(12),
    },
    {
      id: 9034,
      documentId: 'd0c0a1b2-0004-4004-8004-000000000004',
      knowledgeBaseId: IDS.kbProductDocs,
      fileName: 'incident-postmortem-2026-08.md',
      documentStatus: 'uploaded',
      stage: 'uploaded',
      status: 'succeeded',
      message: null,
      details: { sizeBytes: 38_120, contentType: 'text/markdown', source: 'upload' },
      createdAt: hoursAgo(12),
    },
  ],
}
