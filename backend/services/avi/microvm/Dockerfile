# Avi MicroVM image.
#
# Lambda builds this Dockerfile, starts the server, and snapshots the running
# state, so every MicroVM launched from the image resumes with the proxy already
# listening and the agent already imported.
#
# The heavy half — Python, LangChain Deep Agents, LangGraph, boto3 — is the agent
# container built and pushed by `infra/aws/deploy-avi.sh` from
# `backend/avi/Dockerfile`. This Dockerfile only starts that image's processes, so
# the MicroVM build never compiles the Python dependency set (it would not fit the
# build's time or layer budget).
#
# The base image reference is templated in by `infra/aws/deploy-avi.sh`, because
# the Lambda MicroVM image resource reads this Dockerfile from S3 and offers no
# build-arg hook. The placeholder below is replaced with the pushed ECR URI; the
# build role has `ecr:GetAuthorizationToken` plus pull permissions for it.
FROM __AVI_AGENT_IMAGE__

USER root

WORKDIR /app

# The Node streaming proxy is NOT installed here. The agent image already copies
# services/avi/microvm/{package.json,app.mjs} into /app/microvm, runs the
# `npm install` for them, and then deliberately removes npm to keep the image
# small ("keeps Node but not npm"). Repeating that install in this stage failed
# with `/bin/sh: 1: npm: not found` (exit 127) and broke the image build.

# The MicroVM's ingress port. The agent itself listens on AVI_PORT (8000) on the
# loopback only, so the proxy is the single entry point.
ENV PORT=8080
EXPOSE 8080

# Lambda waits for this before snapshotting the image, so readiness is declared
# rather than raced. The proxy answers /ping from the agent's own /ping.
#
# Probed with Node rather than wget/curl: the base is python:3.13-slim, which
# ships neither. The agent image does provide Node, and Node 22 has global fetch.
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:'+(process.env.PORT||8080)+'/ping').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]

# The agent image's entrypoint starts the agent and the proxy; keep it as the
# single source of truth for process supervision.
CMD ["/usr/local/bin/avi-entrypoint"]
