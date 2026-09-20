/**
 * Shared streaming-proxy core used by the Lambda MicroVM host.
 *
 * The MicroVM serves an HTTP endpoint (see `microvm/app.mjs`). Each request
 * carries the caller's Auth0 access token; this module verifies it against the
 * tenant JWKS, derives the per-user AgentCore session id, then opens a
 * streaming invocation against the AgentCore runtime and hands the upstream
 * body back to the caller.
 *
 * AWS Lambda MicroVMs run for up to 8 hours, so unlike a Lambda Function
 * (15-minute cap) this path can hold a long agent run open. The AgentCore
 * session itself is capped by the runtime's `max_lifetime` (25 min).
 *
 * Configuration (environment):
 *   AGENT_RUNTIME_ARN            AgentCore runtime ARN (required)
 *   AGENT_RUNTIME_QUALIFIER      AgentCore endpoint/alias (default DEFAULT)
 *   AGENT_RUN_TIMEOUT_SECONDS    Abort the upstream stream after this (default 1500)
 *   AUTH0_DISCOVERY_URL          OIDC discovery document (required)
 *   AUTH0_AUDIENCE               Comma-separated allowed audiences
 *   AUTH0_ISSUER                 Optional issuer override
 *   AWS_REGION / AWS_DEFAULT_REGION
 */

import {
  createHash,
  createPublicKey,
  randomUUID,
  verify as cryptoVerify,
} from 'node:crypto'

const REGION =
  process.env.AGENT_REGION ||
  process.env.AWS_REGION ||
  process.env.AWS_DEFAULT_REGION ||
  ''
const RUNTIME_ARN = process.env.AGENT_RUNTIME_ARN || ''
const QUALIFIER = process.env.AGENT_RUNTIME_QUALIFIER || 'DEFAULT'
const TIMEOUT_MS = Number(process.env.AGENT_RUN_TIMEOUT_SECONDS || '1500') * 1000

// Discovery/JWKS documents are cached in the process. JWKS is short-lived
// because Auth0 rotates signing keys.
const DISCOVERY_TTL_MS = 3600 * 1000
const JWKS_TTL_MS = 300 * 1000

let discoveryCache = { doc: null, at: 0 }
let jwksCache = { doc: null, at: 0 }

export function agentRunConfigured() {
  return Boolean(RUNTIME_ARN && REGION)
}

export function invocationsUrl() {
  return (
    `https://bedrock-agentcore.${REGION}.amazonaws.com` +
    `/runtimes/${encodeURIComponent(RUNTIME_ARN)}/invocations?qualifier=${QUALIFIER}`
  )
}

export function bearer(value) {
  if (!value) return ''
  const parts = String(value).split(' ')
  if (parts.length > 1 && parts[0].toLowerCase() === 'bearer') {
    return parts.slice(1).join(' ').trim()
  }
  return String(value).trim()
}

/**
 * AgentCore microVM session id, bound to the authenticated user.
 *
 * Deriving it from the verified `sub` keeps affinity (the same user +
 * conversation resumes the same session) while making it unguessable and
 * per-user. 64 hex chars.
 */
export function sessionId(sub, conversationId) {
  const scope = conversationId || randomUUID()
  return createHash('sha256').update(`${sub}:${scope}`).digest('hex')
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { accept: 'application/json' } })
  if (!response.ok) throw new Error(`HTTP ${response.status} for ${url}`)
  return response.json()
}

async function discovery() {
  const now = Date.now()
  if (discoveryCache.doc && now - discoveryCache.at < DISCOVERY_TTL_MS) {
    return discoveryCache.doc
  }
  const url = (process.env.AUTH0_DISCOVERY_URL || '').trim()
  if (!url) throw new Error('AUTH0_DISCOVERY_URL is not configured')
  const doc = await fetchJson(url)
  discoveryCache = { doc, at: now }
  return doc
}

async function jwks() {
  const now = Date.now()
  if (jwksCache.doc && now - jwksCache.at < JWKS_TTL_MS) return jwksCache.doc
  const uri = String((await discovery()).jwks_uri || '')
  if (!uri) throw new Error('discovery document has no jwks_uri')
  const document = await fetchJson(uri)
  jwksCache = { doc: document, at: now }
  return document
}

function audiences() {
  return (process.env.AUTH0_AUDIENCE || '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

function decodeSegment(segment) {
  return JSON.parse(Buffer.from(segment, 'base64url').toString('utf8'))
}

/**
 * Return the verified claims, or throw. ``jwks``/``audience``/``issuer`` are
 * injectable for tests; production calls pass only the token and read the rest
 * from the environment.
 */
export async function verifyToken(token, options = {}) {
  if (!token || String(token).split('.').length !== 3) {
    throw new Error('malformed token')
  }
  const [headerB64, payloadB64, signatureB64] = String(token).split('.')
  const header = decodeSegment(headerB64)
  // Pin the algorithm: never accept ``none`` or an HMAC token signed with the
  // (public) RSA key material.
  if (header.alg !== 'RS256') throw new Error('unsupported token algorithm')

  const document = options.jwks ?? (await jwks())
  const key = (document.keys || []).find((candidate) => candidate.kid === header.kid)
  if (!key) throw new Error('no matching signing key')

  const publicKey = createPublicKey({ key, format: 'jwk' })
  const valid = cryptoVerify(
    'RSA-SHA256',
    Buffer.from(`${headerB64}.${payloadB64}`),
    publicKey,
    Buffer.from(signatureB64, 'base64url'),
  )
  if (!valid) throw new Error('signature verification failed')

  const claims = decodeSegment(payloadB64)
  const now = Math.floor(Date.now() / 1000)
  if (claims.exp === undefined || claims.exp <= now) throw new Error('token expired')
  if (claims.nbf !== undefined && claims.nbf > now) throw new Error('token not yet valid')

  const issuer =
    options.issuer ?? process.env.AUTH0_ISSUER ?? String((await discovery()).issuer || '')
  if (issuer && claims.iss !== issuer) throw new Error('invalid issuer')

  const audience = options.audience ?? audiences()
  if (audience.length) {
    const claimAud = Array.isArray(claims.aud) ? claims.aud : [claims.aud]
    if (!claimAud.some((value) => audience.includes(value))) {
      throw new Error('invalid audience')
    }
  }
  if (!claims.sub) throw new Error('missing subject')
  return claims
}

/**
 * Verify the caller and open a streaming AgentCore invocation.
 *
 * Returns either `{ status, error }` for a failure (the caller renders it as an
 * SSE `run.error` frame) or `{ status: 200, stream }` where `stream` is a web
 * `ReadableStream` of the upstream SSE body.
 */
export async function handleInvocation({ authorization, body }) {
  if (!agentRunConfigured()) {
    return { status: 500, error: 'Agent runtime is not configured' }
  }
  if (!authorization) {
    return { status: 401, error: 'Missing Authorization header' }
  }

  let claims
  try {
    claims = await verifyToken(bearer(authorization))
  } catch (error) {
    console.log(
      JSON.stringify({ level: 'warning', message: 'token rejected', error: String(error) }),
    )
    return { status: 401, error: 'Unauthorized' }
  }

  let payload = {}
  try {
    const parsed = JSON.parse(body || '{}')
    if (parsed && typeof parsed === 'object') payload = parsed
  } catch {
    payload = {}
  }
  const sid = sessionId(String(claims.sub || ''), String(payload.conversationId || '').trim())

  let response
  try {
    response = await fetch(invocationsUrl(), {
      method: 'POST',
      headers: {
        authorization,
        'content-type': 'application/json',
        accept: 'text/event-stream',
        'x-amzn-bedrock-agentcore-runtime-session-id': sid,
      },
      body,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    })
  } catch (error) {
    return { status: 502, error: `Could not reach agent runtime: ${error?.message || error}` }
  }

  if (!response.ok) {
    const detail = (await response.text().catch(() => '')).slice(0, 500)
    return { status: 502, error: `Agent runtime returned HTTP ${response.status}: ${detail}` }
  }
  return { status: 200, stream: response.body }
}
