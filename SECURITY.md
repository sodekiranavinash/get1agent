# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security vulnerabilities.

Report privately using GitHub's [private vulnerability
reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability):

1. Go to the **Security** tab of this repository.
2. Click **Report a vulnerability**.
3. Describe the issue with as much detail as you can.

We will acknowledge your report as quickly as possible and keep you updated on the remediation. We
ask that you give us reasonable time to investigate and fix the issue before any public disclosure.

## What to include

- A clear description of the vulnerability and its impact.
- Steps to reproduce (a proof of concept if you have one).
- The affected component, route, or file.
- Any suggested remediation, if you have one.

## Scope

In scope:

- The backend services under `backend/` (Lambda handlers, shared packages, agents runtime).
- The frontend under `frontend/`.
- The infrastructure definitions under `infra/`.

Out of scope:

- Vulnerabilities in third-party dependencies that are already publicly known (please report those
  upstream).
- Findings that require a compromised machine, a malicious browser extension, or physical access.
- Denial of service through sheer volume; volumetric protection is handled at the API Gateway.

## Our practices

- Authentication is enforced at the API edge (Auth0 JWT) and validated again inside the agent
  runtime.
- User secrets are KMS-encrypted and never returned in plaintext by the API.
- LLM-generated code runs in an isolated sandbox (Bedrock AgentCore microVMs, or a resource-limited
  subprocess locally) behind an AST guard and an audit hook.
- Outbound fetches are guarded against SSRF, with the connection pinned to a validated IP.

Thank you for helping keep get1agent and its users safe.
