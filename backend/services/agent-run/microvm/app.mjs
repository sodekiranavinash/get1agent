/**
 * Lambda MicroVM host for the agent-run streaming proxy.
 *
 * Runs a small HTTP server inside the MicroVM. Unlike a Lambda Function
 * (15-minute cap), a MicroVM can run for up to 8 hours, so this path holds long
 * agent runs open. The AgentCore session is capped by the runtime's
 * `max_lifetime` (25 min).
 *
 * Routes:
 *   GET  /ping          health/readiness
 *   POST /invocations   verify the Auth0 token, stream the AgentCore SSE back
 *
 * All ingress requests must also carry the AWS `X-aws-proxy-auth` token minted
 * by the control plane (`backend/services/agent-run/index.mjs`); the platform
 * rejects requests without it before they reach this app.
 */

import http from 'node:http'

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
    const result = await handleInvocation({
      authorization: request.headers.authorization,
      body,
    })

    if (!result.stream) {
      response.writeHead(result.status, {
        ...cors,
        'content-type': 'text/event-stream',
        'cache-control': 'no-cache',
      })
      response.end(errorFrame(result.error))
      return
    }

    response.writeHead(200, {
      ...cors,
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
      connection: 'keep-alive',
    })
    const reader = result.stream.getReader()
    try {
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        response.write(value)
      }
    } catch (error) {
      response.write(errorFrame(String(error?.message || error)))
    }
    response.end()
    return
  }

  response.writeHead(404, cors)
  response.end()
})

server.listen(PORT, () => {
  console.log(`agent-run microvm listening on ${PORT}`)
})
