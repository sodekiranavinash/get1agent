/**
 * The technologies behind get1agent, grouped for the landing + architecture pages.
 *
 * The platform is **fully AWS-native**: every model call, embedding, rerank,
 * web search and trace runs on Amazon Bedrock / AgentCore / CloudWatch. Auth0
 * (identity) and Cloudflare (DNS/CDN) are the only deliberate external
 * dependencies.
 */
export const TECH_STACK = [
  {
    label: 'Frontend',
    items: ['React', 'TypeScript', 'Vite', 'Tailwind CSS', 'React Flow', 'CodeMirror'],
  },
  {
    label: 'AI · Bedrock',
    items: [
      'Titan embeddings',
      'Titan Multimodal',
      'Bedrock Rerank',
      'Bedrock Web Search',
      'Nova · DeepSeek · Qwen · GLM',
      'Guardrails',
      'Prompt caching',
      'Structured outputs',
      'Batch inference',
    ],
  },
  {
    label: 'AgentCore',
    items: [
      'Runtime',
      'Code Interpreter',
      'Memory',
      'Policy',
      'Gateway',
      'Identity',
      'Registry',
      'Evaluations',
      'Optimization',
      'Browser',
    ],
  },
  {
    label: 'Compute',
    items: ['Lambda', 'API Gateway', 'Step Functions', 'EventBridge', 'SQS', 'Lambda MicroVMs', 'ECR'],
  },
  {
    label: 'Data',
    items: ['DynamoDB', 'S3', 'S3 Vectors', 'KMS', 'DynamoDB TTL'],
  },
  {
    label: 'Observability',
    items: ['CloudWatch', 'X-Ray', 'OTel (ADOT)', 'EMF metrics'],
  },
  {
    label: 'Delivery',
    items: ['Terraform', 'GitHub Actions', 'Docker', 'Floci', 'moto'],
  },
  {
    label: 'External (by choice)',
    items: ['Auth0', 'Cloudflare'],
  },
] as const

/** The headline used across the landing and architecture pages. */
export const AWS_SERVICE_HEADLINE = 'Built on 10+ AWS services'
export const AWS_NATIVE_LINE =
  'Fully AWS-native — every model call, embedding, rerank and trace runs on Amazon Bedrock and AgentCore.'
