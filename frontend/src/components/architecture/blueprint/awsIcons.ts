/**
 * Official AWS Architecture Icons, from the `@aws-icons/react` package
 * (mirrors the AWS Architecture Icons published at
 * https://aws.amazon.com/architecture/icons/). AWS icons are
 * © Amazon Web Services, Inc. and used under the AWS icon terms.
 *
 * Only the handful of services this platform actually runs on are imported, so
 * the bundle stays tree-shaken. Components that are not AWS (the browser, the
 * identity provider, the model/search/embedding/tracing services) deliberately
 * keep the neutral symbol so the map never implies a vendor we may swap.
 */
import { AmazonApiGateway } from '@aws-icons/react/architecture-service/amazon-api-gateway'
import { AmazonDynamoDb } from '@aws-icons/react/architecture-service/amazon-dynamo-db'
import { AmazonSimpleStorageService } from '@aws-icons/react/architecture-service/amazon-simple-storage-service'
import { AmazonEventBridge } from '@aws-icons/react/architecture-service/amazon-event-bridge'
import { AmazonSimpleQueueService } from '@aws-icons/react/architecture-service/amazon-simple-queue-service'
import { AwsKeyManagementService } from '@aws-icons/react/architecture-service/aws-key-management-service'
import { AwsStepFunctions } from '@aws-icons/react/architecture-service/aws-step-functions'
import { AwsLambda } from '@aws-icons/react/architecture-service/aws-lambda'
import { AmazonBedrockAgentCore } from '@aws-icons/react/architecture-service/amazon-bedrock-agent-core'
import { AmazonCloudWatch } from '@aws-icons/react/architecture-service/amazon-cloud-watch'
import { AwsXRay } from '@aws-icons/react/architecture-service/aws-x-ray'
import { AmazonBedrock } from '@aws-icons/react/architecture-service/amazon-bedrock'
import type { AwsIconComponent } from '@aws-icons/react'

export const AWS_ICONS = {
  lambda: AwsLambda,
  apiGateway: AmazonApiGateway,
  dynamodb: AmazonDynamoDb,
  s3: AmazonSimpleStorageService,
  eventbridge: AmazonEventBridge,
  sqs: AmazonSimpleQueueService,
  kms: AwsKeyManagementService,
  stepFunctions: AwsStepFunctions,
  agentcore: AmazonBedrockAgentCore,
  cloudwatch: AmazonCloudWatch,
  xray: AwsXRay,
  bedrock: AmazonBedrock,
} satisfies Record<string, AwsIconComponent>

export type AwsIconId = keyof typeof AWS_ICONS
