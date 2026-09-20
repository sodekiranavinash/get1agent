/**
 * Agent-run control plane.
 *
 * Invoked through **API Gateway** (`POST /v1/agent-run/session`) behind the
 * Auth0 JWT authorizer, so authentication happens at the gateway — this Lambda
 * does one thing: launch a Lambda MicroVM from the agent-run image and return
 * its endpoint plus a short-lived ingress token.
 *
 * The browser cannot mint the MicroVM `X-aws-proxy-auth` token itself (it needs
 * IAM credentials), so this thin, gateway-protected endpoint does it. The
 * browser then streams directly from the MicroVM (`microvm/app.mjs`), which runs
 * for up to 8 hours — past the 15-minute Lambda Function limit.
 *
 * Response: { "endpoint": "...", "token": "...", "expiresAt": "..." }
 */

import {
  CreateMicrovmAuthTokenCommand,
  GetMicrovmCommand,
  LambdaMicroVMsClient,
  RunMicrovmCommand,
} from '@aws-sdk/client-lambda-microvms'

const REGION = process.env.AWS_REGION || process.env.AWS_DEFAULT_REGION || ''
const IMAGE_ARN = process.env.AGENT_MICROVM_IMAGE_ARN || ''
const TOKEN_TTL_MINUTES = Number(process.env.AGENT_MICROVM_TOKEN_TTL_MINUTES || '25')
const MAX_RUN_SECONDS = Number(process.env.AGENT_MICROVM_MAX_DURATION_SECONDS || '1800')
// API Gateway HTTP APIs cap the integration at 30s, so stay comfortably under it.
const READY_TIMEOUT_MS = 20_000

const client = new LambdaMicroVMsClient({ region: REGION })

const INGRESS = [
  `arn:aws:lambda:${REGION}:aws:network-connector:aws-network-connector:ALL_INGRESS`,
]
const EGRESS = [
  `arn:aws:lambda:${REGION}:aws:network-connector:aws-network-connector:INTERNET_EGRESS`,
]

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function json(statusCode, body) {
  return {
    statusCode,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  }
}

/** Launch a MicroVM and wait (briefly) for it to accept traffic. */
async function launchMicrovm() {
  const run = await client.send(
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
    await sleep(500)
    const info = await client.send(new GetMicrovmCommand({ microvmIdentifier: run.microvmId }))
    state = info.state
    endpoint = info.endpoint || endpoint
  }
  if (state !== 'RUNNING') throw new Error(`MicroVM did not become ready (state=${state})`)
  return { microvmId: run.microvmId, endpoint }
}

export const handler = async () => {
  if (!IMAGE_ARN || !REGION) {
    return json(500, { error: 'Agent MicroVM is not configured' })
  }
  try {
    const { microvmId, endpoint } = await launchMicrovm()
    const result = await client.send(
      new CreateMicrovmAuthTokenCommand({
        microvmIdentifier: microvmId,
        expirationInMinutes: TOKEN_TTL_MINUTES,
        allowedPorts: [{ allPorts: {} }],
      }),
    )
    const expiresAt = new Date(Date.now() + TOKEN_TTL_MINUTES * 60 * 1000).toISOString()
    return json(200, { endpoint, token: result.authToken, expiresAt })
  } catch (error) {
    console.log(
      JSON.stringify({ level: 'error', message: 'session start failed', error: String(error) }),
    )
    return json(502, { error: 'Could not start an agent session' })
  }
}
