/**
 * Lambda MicroVM host for the agent-run streaming proxy.
 *
 * Runs a small HTTP + WebSocket server inside the MicroVM. A Lambda Function is
 * capped at 15 minutes; a MicroVM runs up to 8 hours, so this path holds long
 * agent runs open. The AgentCore session is capped by the runtime's
 * `max_lifetime` (25 min).
 *
 * Transports:
 *   GET  /ping          health/readiness
 *   POST /invocations   HTTP + `X-aws-proxy-auth` (curl / non-browser clients)
 *   WS   /invocations   browser transport: the MicroVM ingress auth token
 *                       cannot be sent as an HTTP header cross-origin (CORS
 *                       preflight strips it), so browsers use a WebSocket and
 *                       carry the token in the `lambda-microvms.authentication.*`
 *                       subprotocol. The first WS message is
 *                       `{ token: <Auth0>, payload: { agentId, input, ... } }`.
 */

import http from 'node:http'

import { WebSocketServer } from 'ws'

import { agentRunConfigured, handleInvocation } from '../proxy.mjs'

const PORT = Number(process.env.PORT || '8080')
const ALLOWED_ORIGINS = (process.env.AGENT_RUN_ALLOWED_ORIGINS || '*')
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
    'access-control-allow-headers':
      'authorization, content-type, x-aws-proxy-auth, x-agent-session, accept',
    'access-control-max-age': '3600',
    vary: 'origin',
  }
}

function errorFrame(message) {
  return `event: error\ndata: ${JSON.stringify({ type: 'run.error', message })}\n\n`
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = []
    request.on('data', (chunk) => chunks.push(chunk))
    request.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    request.on('error', reject)
  })
}

/** Verify the caller, open the AgentCore stream and forward frames to `write`. */
async function streamRun({ authorization, body }, write) {
  const result = await handleInvocation({ authorization, body })
  if (!result.stream) {
    write(errorFrame(result.error))
    return
  }
  const reader = result.stream.getReader()
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
    response.writeHead(200, { ...cors, 'content-type': 'application/json' })
    response.end(JSON.stringify({ status: 'ok', configured: agentRunConfigured() }))
    return
  }

  if (request.method === 'POST' && (path === '/invocations' || path === '/')) {
    const body = await readBody(request).catch(() => '')
    let started = false
    response.writeHead(200, {
      ...cors,
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
      connection: 'keep-alive',
    })
    await streamRun(
      { authorization: request.headers.authorization, body },
      (chunk) => {
        if (!started) started = true
        response.write(chunk)
      },
    )
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
  console.log(`agent-run microvm listening on ${PORT}`)
})
