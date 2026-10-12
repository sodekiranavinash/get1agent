/**
 * Avi MicroVM host — the streaming ingress for every signed-in and guest turn.
 *
 * Why a MicroVM rather than the Lambda Function URL: API Gateway HTTP APIs cannot
 * stream and cap an integration at 30 s, and a Lambda Function is capped at
 * 15 minutes. A MicroVM serves a long turn and streams tokens from the first one.
 *
 * It is a **pure proxy**. Identity, classification, retrieval and persistence all
 * live in the agent container (`backend/avi`, FastAPI on :8080); this file only
 * moves bytes and adds CORS. That keeps exactly one implementation of who-is-
 * asking and how-an-answer-is-produced, shared by both audiences:
 *
 *   signed-in  the browser sends `Authorization: Bearer <session>` (minted by the
 *              control plane after the gateway verified the Auth0 JWT)
 *   guest      the ingress exchanges its request for a signed **guest badge** at
 *              `/v1/avi/badge`, so the agent service verifies a signature in both
 *              cases instead of trusting a header
 *
 * Transports:
 *   GET  /ping          health/readiness (also proxies the agent's own /ping)
 *   POST /invocations   HTTP + `X-aws-proxy-auth` (curl / non-browser clients)
 *   WS   /invocations   browser transport: the MicroVM ingress token cannot be
 *                       sent as a cross-origin HTTP header (CORS preflight strips
 *                       it), so browsers use a WebSocket carrying the token in the
 *                       `lambda-microvms.authentication.*` subprotocol. The first
 *                       message is `{ token, payload }`.
 */

import http from 'node:http'

import { WebSocketServer } from 'ws'

const PORT = Number(process.env.PORT || '8080')
const AGENT_URL = (process.env.AVI_AGENT_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
const ALLOWED_ORIGINS = (process.env.AVI_ALLOWED_ORIGINS || '*')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean)

function corsHeaders(origin) {
  const allow =
    ALLOWED_ORIGINS.includes('*') || !origin
      ? '*'
      : ALLOWED_ORIGINS.includes(origin)
        ? origin
        : ALLOWED_ORIGINS[0]
  return {
    'access-control-allow-origin': allow,
    'access-control-allow-methods': 'POST, GET, OPTIONS',
    'access-control-allow-headers': 'authorization, content-type, x-aws-proxy-auth, accept',
    'access-control-max-age': '3600',
    vary: 'origin',
  }
}

function errorFrame(message) {
  return `data: ${JSON.stringify({ type: 'run.error', message })}\n\n`
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    request.on('error', reject)
  })
}

/**
 * Forward one turn to the agent container and write the SSE bytes back as they
 * arrive. Never buffers: the whole point is that the first token reaches the
 * browser immediately.
 */
async function streamRun({ authorization, body }, write) {
  let upstream
  try {
    upstream = await fetch(`${AGENT_URL}/invocations`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'text/event-stream',
        ...(authorization ? { authorization } : {}),
      },
      body: body || '{}',
    })
  } catch (error) {
    write(errorFrame('Avi is starting up — please try again in a moment.'))
    console.log(JSON.stringify({ level: 'error', message: 'agent unreachable', error: String(error) }))
    return
  }

  if (!upstream.ok || !upstream.body) {
    // The container answers a refusal (429/403/400) as JSON; translate it into
    // the frame contract so the widget has exactly one error shape to render.
    let payload = {}
    try {
      payload = await upstream.json()
    } catch {
      payload = {}
    }
    write(
      `data: ${JSON.stringify({
        type: 'run.error',
        message: payload.error || `Avi is unavailable (${upstream.status})`,
        code: payload.code || 'upstream_error',
        retryable: upstream.status >= 500,
        retryAfterSeconds: payload.retryAfterSeconds || null,
        signInRequired: Boolean(payload.signInRequired),
      })}\n\n`,
    )
    return
  }

  const reader = upstream.body.getReader()
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      write(Buffer.from(value).toString('utf8'))
    }
  } catch (error) {
    write(errorFrame(String(error?.message || error)))
  }
}

const server = http.createServer(async (request, response) => {
  const origin = request.headers.origin
  const cors = corsHeaders(origin)

  if (request.method === 'OPTIONS') {
    response.writeHead(204, cors)
    response.end()
    return
  }

  const path = (request.url || '').split('?')[0]

  if (request.method === 'GET' && path === '/ping') {
    // Report the agent's own view, so /ping answers "is Avi actually usable".
    let agent = null
    try {
      const upstream = await fetch(`${AGENT_URL}/ping`)
      agent = await upstream.json()
    } catch {
      agent = null
    }
    response.writeHead(agent ? 200 : 503, { ...cors, 'content-type': 'application/json' })
    response.end(
      JSON.stringify({ status: agent ? 'ok' : 'starting', configured: Boolean(agent), agent }),
    )
    return
  }

  if (request.method === 'POST' && (path === '/invocations' || path === '/')) {
    const body = await readBody(request).catch(() => '')
    response.writeHead(200, {
      ...cors,
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
      'x-accel-buffering': 'no',
    })
    await streamRun({ authorization: request.headers.authorization, body }, (chunk) => {
      response.write(chunk)
    })
    response.end()
    return
  }

  response.writeHead(404, cors)
  response.end()
})

const wss = new WebSocketServer({ server, path: '/invocations' })

wss.on('connection', (socket) => {
  let started = false
  socket.on('error', () => {})
  socket.on('message', async (raw) => {
    if (started) return
    started = true

    let message
    try {
      message = JSON.parse(raw.toString())
    } catch {
      socket.close(1003, 'invalid message')
      return
    }

    await streamRun(
      {
        authorization: `Bearer ${message.token || ''}`,
        body: JSON.stringify(message.payload || {}),
      },
      (chunk) => {
        if (socket.readyState === socket.OPEN) socket.send(chunk)
      },
    )
    socket.close()
  })
})

server.listen(PORT, () => {
  console.log(`avi microvm listening on ${PORT} -> ${AGENT_URL}`)
})
