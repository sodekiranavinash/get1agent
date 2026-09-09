import { Signer } from '@aws-sdk/rds-signer'
import type {
  APIGatewayProxyEventV2,
  APIGatewayProxyResultV2,
} from 'aws-lambda'
import { Client } from 'pg'

type HealthBody = {
  status: 'ok' | 'error'
  database?: string
  message?: string
}

function json(
  statusCode: number,
  body: HealthBody,
): APIGatewayProxyResultV2 {
  return {
    statusCode,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }
}

function requiredEnv(name: string): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(`Missing required env var: ${name}`)
  }
  return value
}

export async function handler(
  _event: APIGatewayProxyEventV2,
): Promise<APIGatewayProxyResultV2> {
  const host = requiredEnv('DB_HOST')
  const port = Number(process.env.DB_PORT ?? '5432')
  const database = requiredEnv('DB_NAME')
  const user = requiredEnv('DB_IAM_USER')
  const region = requiredEnv('AWS_REGION')

  const signer = new Signer({
    hostname: host,
    port,
    username: user,
    region,
  })

  const client = new Client({
    host,
    port,
    database,
    user,
    password: await signer.getAuthToken(),
    ssl: { rejectUnauthorized: false },
    connectionTimeoutMillis: 5_000,
  })

  try {
    await client.connect()
    await client.query('SELECT 1')
    return json(200, { status: 'ok', database })
  } catch (err) {
    const message = err instanceof Error ? err.message : 'database unavailable'
    console.error('health-check db error:', message)
    return json(503, { status: 'error', message })
  } finally {
    await client.end().catch(() => undefined)
  }
}
