/**
 * Avi control plane.
 *
 * Invoked through **API Gateway** (`POST /v1/avi/session`) behind the Auth0 JWT
 * authorizer, so authentication has already happened at the gateway. This Lambda
 * does three things and nothing else:
 *
 *   1. resolves the verified `sub` to the internal `userId` (`SUB#<sub>`),
 *   2. mints a short-lived signed **session token** carrying that userId,
 *   3. launches the Avi MicroVM and mints its ingress token.
 *
 * The session token is the important part. The agent service must know who is
 * asking, and it must not take the caller's word for it — so it verifies the HMAC
 * on this token instead. That is why the browser never sends a userId, and why a
 * forged `userId` in a request body cannot impersonate anyone.
 *
 * Response: { endpoint, token, session, expiresAt }
 */

import {
  DynamoDBClient,
  GetItemCommand,
  UpdateItemCommand,
} from '@aws-sdk/client-dynamodb'
import sdk from '@aws-sdk/client-lambda-microvms'
import { createHmac } from 'node:crypto'

const {
  CreateMicrovmAuthTokenCommand,
  GetMicrovmCommand,
  LambdaMicrovmsClient,
  RunMicrovmCommand,
} = sdk

const REGION = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || ''
const IMAGE_ARN = process.env.AVI_MICROVM_IMAGE_ARN || ''
const TABLE = process.env.DYNAMODB_TABLE || ''
// Read on each use rather than captured at import: the Python verifier resolves
// it per call, and a value cached here could disagree with it after a rotation.
const sessionSecret = () => process.env.AVI_SESSION_SECRET || ''
const TOKEN_TTL_MINUTES = Number(process.env.AVI_MICROVM_TOKEN_TTL_MINUTES || '25')
const SESSION_TTL_SECONDS = Number(process.env.AVI_SESSION_TTL_SECONDS || '900')
const MAX_RUN_SECONDS = Number(process.env.AVI_MICROVM_MAX_DURATION_SECONDS || '1800')
// API Gateway HTTP APIs cap the integration at 30s, so stay comfortably under it.
const READY_TIMEOUT_MS = 20_000

// Clients are created on first use rather than at module load: a cold start that
// only serves a health check should not pay to construct two SDK clients, and it
// keeps the module importable in a unit test with no AWS credentials.
let microvmClient = null
let dynamoClient = null

const client = () => (microvmClient ??= new LambdaMicrovmsClient({ region: REGION }))
const dynamo = () => (dynamoClient ??= new DynamoDBClient({ region: REGION }))

const INGRESS = [
  `arn:aws:lambda:${REGION}:aws:network-connector:aws-network-connector:ALL_INGRESS`,
]
const EGRESS = [
  `arn:aws:lambda:${REGION}:aws:network-connector:aws-network-connector:INTERNET_EGRESS`,
]

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function json(statusCode, body, headers = {}) {
  return {
    statusCode,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers },
    body: JSON.stringify(body),
  }
}

/** The verified JWT claims API Gateway attached to the request. */
function claimsFrom(event) {
  try {
    return event?.requestContext?.authorizer?.jwt?.claims || null
  } catch {
    return null
  }
}

/** A JSON body from an API Gateway / Function URL event. */
function parseBody(event) {
  const raw = event?.body
  if (!raw) return {}
  try {
    const text = event?.isBase64Encoded
      ? Buffer.from(raw, 'base64').toString('utf8')
      : String(raw)
    const data = JSON.parse(text)
    return data && typeof data === 'object' ? data : {}
  } catch {
    return {}
  }
}

/** Resolve an Auth0 sub to the internal userId through the identity item. */
async function resolveUser(sub) {
  if (!TABLE) throw new Error('DYNAMODB_TABLE is not configured')
  const result = await dynamo().send(
    new GetItemCommand({
      TableName: TABLE,
      Key: { pk: { S: `SUB#${sub}` }, sk: { S: '#IDENTITY' } },
      ConsistentRead: true, // never a GSI: a stale read would create a duplicate
    }),
  )
  const userId = result.Item?.userId?.S
  if (!userId) throw new Error('no account for this identity')
  return userId
}

function isAdmin(claims) {
  const roles = claims?.['https://get1agent.com/roles'] || claims?.roles || []
  const list = Array.isArray(roles) ? roles : String(roles).split(/[\s,]+/)
  return list.some((role) => String(role).toLowerCase() === 'admin')
}

const b64url = (value) => Buffer.from(value).toString('base64url')

/** Mint the signed session token the agent service verifies. */
function mintSession({ sub, userId, claims, guest = false }) {
  const secret = sessionSecret()
  if (!secret) throw new Error('AVI_SESSION_SECRET is not configured')
  const now = Math.floor(Date.now() / 1000)
  const payload = {
    sub,
    userId,
    email: claims?.email || '',
    name: claims?.name || '',
    admin: isAdmin(claims),
    guest,
    iat: now,
    exp: now + SESSION_TTL_SECONDS,
  }
  const body = b64url(JSON.stringify(payload))
  const signature = createHmac('sha256', secret).update(body).digest('base64url')
  return `avi1.${body}.${signature}`
}

/** The caller's IP, from the fields API Gateway and the Function URL provide. */
function sourceIp(event) {
  const headers = Object.fromEntries(
    Object.entries(event?.headers || {}).map(([key, value]) => [key.toLowerCase(), value]),
  )
  const forwarded = String(headers['x-forwarded-for'] || '')
  if (forwarded) return forwarded.split(',')[0].trim()
  return String(event?.requestContext?.http?.sourceIp || '')
}

/**
 * Fixed-window guest counter, keyed by a hash of the caller's IP (never the raw
 * IP). This is the guest's *page-load* budget: one badge buys several turns, and
 * the agent service applies the per-turn budget on top.
 */
async function guestAllowance(event) {
  const perHour = Number(process.env.AVI_GUEST_BADGES_PER_HOUR || '30')
  const ip = sourceIp(event)
  const salt = process.env.AVI_GUEST_SALT || 'avi'
  const bucket = createHmac('sha256', salt).update(ip || 'unknown').digest('hex').slice(0, 24)
  const window = Math.floor(Date.now() / 1000 / 3600)
  const ttl = (window + 2) * 3600

  if (!TABLE) return { allowed: true, bucket }
  try {
    const result = await dynamo().send(
      new UpdateItemCommand({
        TableName: TABLE,
        Key: { pk: { S: 'RATE#avi-badge#guest' }, sk: { S: `W#${window}#${bucket}` } },
        UpdateExpression: 'ADD #n :one SET expiresAt = if_not_exists(expiresAt, :ttl)',
        ExpressionAttributeNames: { '#n': 'n' },
        ExpressionAttributeValues: {
          ':one': { N: '1' },
          ':ttl': { N: String(ttl) },
        },
        ReturnValues: 'UPDATED_NEW',
      }),
    )
    const count = Number(result.Attributes?.n?.N || '1')
    return { allowed: count <= perHour, bucket, count, perHour }
  } catch (error) {
    // Never block a guest on a counter failure: the agent service still enforces
    // its own per-turn budget.
    console.log(
      JSON.stringify({ level: 'warn', message: 'guest counter failed', error: String(error) }),
    )
    return { allowed: true, bucket }
  }
}

/** Launch a MicroVM and mint its ingress token (one round trip for the caller). */
async function startMicrovm() {
  const { microvmId, endpoint } = await launchMicrovm()
  const result = await client().send(
    new CreateMicrovmAuthTokenCommand({
      microvmIdentifier: microvmId,
      expirationInMinutes: TOKEN_TTL_MINUTES,
      allowedPorts: [{ allPorts: {} }],
    }),
  )
  const token =
    result.authToken?.['X-aws-proxy-auth'] ?? Object.values(result.authToken ?? {})[0]
  if (!token) throw new Error('MicroVM auth token was empty')
  return { endpoint, token }
}

/** Exchange a guest request for a short-lived signed badge. */
async function guestBadge(event, body) {
  if (process.env.AVI_GUEST_ENABLED === 'false') {
    return json(403, { error: 'Sign in to ask Avi', code: 'guest_disabled' })
  }
  const allowance = await guestAllowance(event)
  if (!allowance.allowed) {
    return json(
      429,
      {
        error: 'That is a lot of questions! Sign in to keep going.',
        code: 'rate_limited',
        signInRequired: true,
        retryAfterSeconds: 900,
      },
      { 'retry-after': '900' },
    )
  }
  const badge = mintSession({
    sub: '',
    userId: `guest_${allowance.bucket}`,
    claims: {},
    guest: true,
  })
  const expiresAt = new Date(Date.now() + SESSION_TTL_SECONDS * 1000).toISOString()

  // A guest streams from the same MicroVM as a signed-in user, so the badge call
  // returns the ingress pair too — one round trip instead of two, which matters
  // for the first question on the landing page.
  if (body?.withMicrovm) {
    try {
      const ingress = await startMicrovm()
      return json(200, { badge, expiresAt, ...ingress })
    } catch (error) {
      console.log(
        JSON.stringify({ level: 'error', message: 'guest session failed', error: String(error) }),
      )
      return json(502, { error: 'Avi is briefly unavailable', code: 'session_failed' })
    }
  }
  return json(200, { badge, expiresAt })
}

/** Launch a MicroVM and wait (briefly) for it to accept traffic. */
async function launchMicrovm() {
  const run = await client().send(
    new RunMicrovmCommand({
      imageIdentifier: IMAGE_ARN,
      ingressNetworkConnectors: INGRESS,
      egressNetworkConnectors: EGRESS,
      maximumDurationInSeconds: MAX_RUN_SECONDS,
      idlePolicy: {
        autoResumeEnabled: true,
        maxIdleDurationSeconds: 900,
        suspendedDurationSeconds: 300,
      },
    }),
  )

  let endpoint = run.endpoint
  let state = run.state
  const deadline = Date.now() + READY_TIMEOUT_MS
  while (state !== 'RUNNING' && Date.now() < deadline) {
    await sleep(400)
    const info = await client().send(
      new GetMicrovmCommand({ microvmIdentifier: run.microvmId }),
    )
    state = info.state
    endpoint = info.endpoint || endpoint
  }
  if (state !== 'RUNNING') throw new Error(`MicroVM did not become ready (state=${state})`)
  return { microvmId: run.microvmId, endpoint }
}

export const handler = async (event) => {
  if (!IMAGE_ARN || !REGION) {
    return json(500, { error: 'Avi is not configured', code: 'not_configured' })
  }

  // One Lambda, two routes: the path decides which. The badge route is
  // unauthenticated (guests have no account) and throttled much harder by the
  // per-IP counter; every other path requires the gateway-verified JWT.
  const path = String(event?.rawPath || event?.requestContext?.http?.path || '/')
  if (path.endsWith('/badge')) {
    return guestBadge(event, parseBody(event))
  }

  const claims = claimsFrom(event)
  const sub = String(claims?.sub || '').trim()
  if (!sub) {
    return json(401, { error: 'Sign in to ask Avi', code: 'unauthorized' })
  }

  let userId
  try {
    userId = await resolveUser(sub)
  } catch (error) {
    console.log(
      JSON.stringify({ level: 'warn', message: 'avi identity failed', error: String(error) }),
    )
    return json(403, { error: 'No account found for this identity', code: 'no_account' })
  }

  try {
    const { microvmId, endpoint } = await launchMicrovm()
    const result = await client().send(
      new CreateMicrovmAuthTokenCommand({
        microvmIdentifier: microvmId,
        expirationInMinutes: TOKEN_TTL_MINUTES,
        allowedPorts: [{ allPorts: {} }],
      }),
    )
    const token =
      result.authToken?.['X-aws-proxy-auth'] ?? Object.values(result.authToken ?? {})[0]
    if (!token) throw new Error('MicroVM auth token was empty')

    const session = mintSession({ sub, userId, claims })
    const expiresAt = new Date(Date.now() + TOKEN_TTL_MINUTES * 60 * 1000).toISOString()
    return json(200, {
      endpoint,
      token,
      session,
      expiresAt,
      sessionExpiresAt: new Date(
        Date.now() + SESSION_TTL_SECONDS * 1000,
      ).toISOString(),
    })
  } catch (error) {
    console.log(
      JSON.stringify({ level: 'error', message: 'avi session failed', error: String(error) }),
    )
    return json(502, { error: 'Could not start an Avi session', code: 'session_failed' })
  }
}

/**
 * Internal helpers exposed for unit tests only.
 *
 * The signed-token format is a cross-language contract (this file mints, the
 * Python agent service verifies), so it must be testable without AWS. Nothing
 * outside the tests should import this.
 */
export const __test = { mintSession, isAdmin, parseBody, sourceIp, claimsFrom }
