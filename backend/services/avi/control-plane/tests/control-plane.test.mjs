/**
 * Avi control-plane unit tests.
 *
 * The control plane mints the signed session token that the Python agent service
 * verifies, and it is the only place that decides *who a caller is*. So these
 * tests pin the token contract and the negative cases: no identity, no guest
 * escalation, and a body that cannot inject one.
 *
 * No network and no AWS: the SDK clients are created lazily, so importing the
 * module is free and the token helpers can be exercised directly. The handler
 * tests that would launch a MicroVM are deliberately limited to the paths that
 * return before any AWS call.
 */

import assert from 'node:assert/strict'
import { createHmac } from 'node:crypto'
import test from 'node:test'

process.env.AWS_REGION = 'ap-south-1'
process.env.AVI_SESSION_SECRET = 'unit-test-secret'
process.env.AVI_MICROVM_IMAGE_ARN = 'arn:aws:lambda:ap-south-1:1:microvm-image:test'
process.env.DYNAMODB_TABLE = 'get1agent-test'
process.env.AVI_GUEST_SALT = 'unit-test-salt'
process.env.AVI_GUEST_ENABLED = 'true'

const { handler, __test } = await import('../index.mjs')

/** Verify a token the way the Python service does, with an independent HMAC. */
function verify(token, secret = process.env.AVI_SESSION_SECRET) {
  const [prefix, body, signature] = token.split('.')
  assert.equal(prefix, 'avi1')
  const expected = createHmac('sha256', secret).update(body).digest('base64url')
  assert.equal(signature, expected, 'signature must match an independent HMAC')
  return JSON.parse(Buffer.from(body, 'base64url').toString('utf8'))
}

test('a user session token carries the identity and is signed', () => {
  const token = __test.mintSession({
    sub: 'auth0|abc',
    userId: 'u_7k3f9qz2mpx8n4rq',
    claims: { email: 'a@example.com', name: 'A' },
  })
  const payload = verify(token)
  assert.equal(payload.userId, 'u_7k3f9qz2mpx8n4rq')
  assert.equal(payload.sub, 'auth0|abc')
  assert.equal(payload.guest, false)
  assert.equal(payload.admin, false)
  assert.ok(payload.exp > payload.iat, 'must expire')
})

test('an admin claim is reflected, and only from the roles claim', () => {
  assert.equal(__test.isAdmin({}), false)
  assert.equal(
    __test.isAdmin({ 'https://get1agent.com/roles': ['admin'] }),
    true,
  )
  assert.equal(__test.isAdmin({ roles: 'user admin' }), true)
  assert.equal(__test.isAdmin({ roles: ['user'] }), false)
})

test('a guest badge is signed and cannot claim an admin role', () => {
  const token = __test.mintSession({
    sub: '',
    userId: 'guest_abc123',
    claims: {},
    guest: true,
  })
  const payload = verify(token)
  assert.equal(payload.guest, true)
  assert.equal(payload.userId, 'guest_abc123')
  assert.equal(payload.admin, false, 'a guest must never be an admin')
})

test('minting without a signing secret fails loudly', () => {
  const saved = process.env.AVI_SESSION_SECRET
  delete process.env.AVI_SESSION_SECRET
  try {
    assert.throws(() => __test.mintSession({ sub: 'x', userId: 'u_1', claims: {} }))
  } finally {
    process.env.AVI_SESSION_SECRET = saved
  }
})

test('a body is parsed, including base64 and junk', () => {
  assert.deepEqual(__test.parseBody({ body: '{"withMicrovm":true}' }), {
    withMicrovm: true,
  })
  assert.deepEqual(
    __test.parseBody({
      body: Buffer.from('{"a":1}').toString('base64'),
      isBase64Encoded: true,
    }),
    { a: 1 },
  )
  assert.deepEqual(__test.parseBody({ body: 'not json' }), {})
  assert.deepEqual(__test.parseBody({}), {})
  assert.deepEqual(__test.parseBody({ body: '"a string"' }), {})
})

test('the caller IP comes from x-forwarded-for before sourceIp', () => {
  assert.equal(
    __test.sourceIp({
      headers: { 'X-Forwarded-For': '203.0.113.7, 10.0.0.1' },
      requestContext: { http: { sourceIp: '10.0.0.2' } },
    }),
    '203.0.113.7',
  )
  assert.equal(
    __test.sourceIp({ requestContext: { http: { sourceIp: '10.0.0.2' } } }),
    '10.0.0.2',
  )
})

test('an unauthenticated session request is refused without touching AWS', async () => {
  const response = await handler({
    rawPath: '/v1/avi/session',
    requestContext: { http: { path: '/v1/avi/session' } },
  })
  assert.equal(response.statusCode, 401)
  assert.equal(JSON.parse(response.body).code, 'unauthorized')
})

test('the guest route is never treated as an authenticated one', async () => {
  // `withMicrovm: false` returns before any AWS call, so this asserts routing and
  // that a guest is not sent down the JWT path (which would be a 401).
  const response = await handler({
    rawPath: '/v1/avi/badge',
    requestContext: { http: { path: '/v1/avi/badge', sourceIp: '203.0.113.7' } },
    body: JSON.stringify({ withMicrovm: false }),
  })
  assert.equal(response.statusCode, 200)
  const body = JSON.parse(response.body)
  assert.ok(body.badge, 'a badge must be returned')
  const payload = verify(body.badge)
  assert.equal(payload.guest, true)
  assert.ok(payload.userId.startsWith('guest_'))
})

test('guests can be switched off by configuration', async () => {
  process.env.AVI_GUEST_ENABLED = 'false'
  const response = await handler({
    rawPath: '/v1/avi/badge',
    requestContext: { http: { path: '/v1/avi/badge', sourceIp: '203.0.113.9' } },
    body: '{}',
  })
  assert.equal(response.statusCode, 403)
  assert.equal(JSON.parse(response.body).code, 'guest_disabled')
  process.env.AVI_GUEST_ENABLED = 'true'
})
