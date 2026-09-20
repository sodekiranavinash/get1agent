/**
 * Unit tests for the agent-run proxy core: token verification, session binding
 * and the AgentCore forwarding path.
 */

import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash, generateKeyPairSync, sign as cryptoSign } from 'node:crypto'

process.env.AWS_REGION = 'ap-south-1'
process.env.AGENT_RUNTIME_ARN =
  'arn:aws:bedrock-agentcore:ap-south-1:626829991663:runtime/get1agent_prod_agent_worker-iEEOf0F1gr'
process.env.AGENT_RUNTIME_QUALIFIER = 'DEFAULT'
process.env.AGENT_RUN_TIMEOUT_SECONDS = '30'
process.env.AUTH0_DISCOVERY_URL = 'https://example.test/.well-known/openid-configuration'
process.env.AUTH0_AUDIENCE = 'https://api.get1agent.com'
process.env.AUTH0_ISSUER = 'https://example.test/'

const { handleInvocation, sessionId, verifyToken } = await import('../proxy.mjs')

const ISSUER = 'https://example.test/'
const AUDIENCE = 'https://api.get1agent.com'
const KID = 'test-key'

const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 })
const jwk = { ...publicKey.export({ format: 'jwk' }), kid: KID, use: 'sig', alg: 'RS256' }
const jwks = { keys: [jwk] }

function b64url(value) {
  return Buffer.from(value).toString('base64url')
}

function makeToken(privateKey, { alg = 'RS256', ...overrides } = {}) {
  const now = Math.floor(Date.now() / 1000)
  const header = b64url(JSON.stringify({ alg, kid: KID, typ: 'JWT' }))
  const claims = {
    sub: 'auth0|abc',
    iss: ISSUER,
    aud: AUDIENCE,
    iat: now,
    exp: now + 300,
    ...overrides,
  }
  const payload = b64url(JSON.stringify(claims))
  const signature =
    alg === 'none'
      ? ''
      : cryptoSign('RSA-SHA256', Buffer.from(`${header}.${payload}`), privateKey)
  return `${header}.${payload}.${b64url(signature)}`
}

function verify(token, overrides = {}) {
  return verifyToken(token, { jwks, issuer: ISSUER, audience: [AUDIENCE], ...overrides })
}

test('valid token returns claims', async () => {
  const claims = await verify(makeToken(privateKey))
  assert.equal(claims.sub, 'auth0|abc')
})

test('wrong audience rejected', async () => {
  await assert.rejects(verify(makeToken(privateKey, { aud: 'https://other.example' })))
})

test('expired token rejected', async () => {
  await assert.rejects(
    verify(makeToken(privateKey, { exp: Math.floor(Date.now() / 1000) - 10 })),
  )
})

test('wrong issuer rejected', async () => {
  await assert.rejects(verify(makeToken(privateKey, { iss: 'https://evil.example/' })))
})

test('signature from another key rejected', async () => {
  const other = generateKeyPairSync('rsa', { modulusLength: 2048 })
  await assert.rejects(verify(makeToken(other.privateKey)))
})

test('unknown kid rejected', async () => {
  await assert.rejects(verify(makeToken(privateKey, {}), { jwks: { keys: [] } }))
})

test('alg none rejected', async () => {
  await assert.rejects(verify(makeToken(privateKey, { alg: 'none' })))
})

test('malformed token rejected', async () => {
  for (const bad of ['', 'not-a-token', 'a.b.c']) {
    await assert.rejects(verify(bad))
  }
})

test('session id is deterministic per user and conversation', () => {
  const first = sessionId('auth0|abc', '42')
  assert.equal(first, sessionId('auth0|abc', '42'))
  assert.equal(first.length, 64)
})

test('session ids do not collide across users or conversations', () => {
  assert.notEqual(sessionId('auth0|abc', '42'), sessionId('auth0|xyz', '42'))
  assert.notEqual(sessionId('auth0|abc', '42'), sessionId('auth0|abc', '43'))
})

test('handleInvocation streams the upstream body with the derived session id', async () => {
  const SSE = 'event: text\ndata: {"type":"text","data":"hi"}\n\n'
  let forwarded = null
  globalThis.fetch = async (url, options = {}) => {
    if (String(url).includes('openid-configuration')) {
      return new Response(JSON.stringify({ issuer: ISSUER, jwks_uri: 'https://example.test/jwks' }), {
        status: 200,
      })
    }
    if (String(url).includes('/jwks')) return new Response(JSON.stringify(jwks), { status: 200 })
    forwarded = { url: String(url), options }
    return new Response(SSE, { status: 200 })
  }

  const token = makeToken(privateKey)
  const result = await handleInvocation({
    authorization: `Bearer ${token}`,
    body: JSON.stringify({ conversationId: '42' }),
  })

  assert.equal(result.status, 200)
  const text = await new Response(result.stream).text()
  assert.equal(text, SSE)
  assert.ok(forwarded.url.includes(encodeURIComponent(process.env.AGENT_RUNTIME_ARN)))
  assert.equal(forwarded.options.headers.authorization, `Bearer ${token}`)
  assert.equal(
    forwarded.options.headers['x-amzn-bedrock-agentcore-runtime-session-id'],
    createHash('sha256').update('auth0|abc:42').digest('hex'),
  )
})

test('handleInvocation rejects a missing or bad token without calling the runtime', async () => {
  let hops = 0
  globalThis.fetch = async (url) => {
    if (String(url).includes('openid-configuration')) {
      return new Response(JSON.stringify({ issuer: ISSUER, jwks_uri: 'https://example.test/jwks' }), {
        status: 200,
      })
    }
    if (String(url).includes('/jwks')) return new Response(JSON.stringify(jwks), { status: 200 })
    hops += 1
    return new Response('', { status: 200 })
  }

  const missing = await handleInvocation({ authorization: '', body: '{}' })
  assert.equal(missing.status, 401)

  const bad = await handleInvocation({ authorization: 'Bearer nope', body: '{}' })
  assert.equal(bad.status, 401)
  assert.equal(hops, 0)
})
