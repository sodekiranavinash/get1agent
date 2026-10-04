import { AmazonBedrock } from '@aws-icons/react/architecture-service/amazon-bedrock'
import { AmazonBedrockAgentCore } from '@aws-icons/react/architecture-service/amazon-bedrock-agent-core'
import { AwsLambda } from '@aws-icons/react/architecture-service/aws-lambda'
import { AmazonApiGateway } from '@aws-icons/react/architecture-service/amazon-api-gateway'
import { AmazonDynamoDb } from '@aws-icons/react/architecture-service/amazon-dynamo-db'
import { AmazonSimpleStorageService } from '@aws-icons/react/architecture-service/amazon-simple-storage-service'
import { AmazonCloudWatch } from '@aws-icons/react/architecture-service/amazon-cloud-watch'
import { AwsXRay } from '@aws-icons/react/architecture-service/aws-x-ray'
import { AwsStepFunctions } from '@aws-icons/react/architecture-service/aws-step-functions'
import { AmazonSimpleQueueService } from '@aws-icons/react/architecture-service/amazon-simple-queue-service'
import { AmazonEventBridge } from '@aws-icons/react/architecture-service/amazon-event-bridge'
import { AwsKeyManagementService } from '@aws-icons/react/architecture-service/aws-key-management-service'
import { AmazonElasticContainerRegistry } from '@aws-icons/react/architecture-service/amazon-elastic-container-registry'
import type { AwsIconComponent } from '@aws-icons/react'

export type AwsServiceEntry = {
  name: string
  note: string
  Icon: AwsIconComponent
}

/**
 * The headline AWS services the platform runs on, with the official AWS
 * Architecture Icons (© Amazon Web Services, Inc.). Used by the landing page's
 * "built on AWS" strip and the architecture page.
 */
export const AWS_SERVICES: AwsServiceEntry[] = [
  { name: 'Amazon Bedrock', note: 'models · embeddings · rerank · guardrails', Icon: AmazonBedrock },
  { name: 'Bedrock AgentCore', note: 'runtime · memory · policy · gateway', Icon: AmazonBedrockAgentCore },
  { name: 'AWS Lambda', note: 'every serverless service', Icon: AwsLambda },
  { name: 'API Gateway', note: 'auth · routing · throttling', Icon: AmazonApiGateway },
  { name: 'DynamoDB', note: 'single-table metadata', Icon: AmazonDynamoDb },
  { name: 'Amazon S3', note: 'objects · index · transcripts', Icon: AmazonSimpleStorageService },
  { name: 'CloudWatch', note: 'logs · metrics · GenAI obs.', Icon: AmazonCloudWatch },
  { name: 'AWS X-Ray', note: 'end-to-end tracing', Icon: AwsXRay },
  { name: 'Step Functions', note: 'ingestion orchestration', Icon: AwsStepFunctions },
  { name: 'Amazon SQS', note: 'queues + dead-letter', Icon: AmazonSimpleQueueService },
  { name: 'EventBridge', note: 'events + scheduler', Icon: AmazonEventBridge },
  { name: 'AWS KMS', note: 'encryption keys', Icon: AwsKeyManagementService },
  { name: 'Amazon ECR', note: 'runtime images', Icon: AmazonElasticContainerRegistry },
]

/** The rest, named only (keeps the strip honest without a wall of logos). */
export const AWS_SERVICES_MORE = [
  'S3 Vectors',
  'Lambda MicroVMs',
  'Bedrock Guardrails',
  'Bedrock Web Search',
  'AgentCore Identity',
  'AgentCore Registry',
  'AgentCore Evaluations',
  'AgentCore Browser',
  'CloudWatch Transaction Search',
  'IAM',
]
