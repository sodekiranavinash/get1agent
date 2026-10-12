# Avi MicroVM image.
#
# Lambda builds this Dockerfile, starts the server, and snapshots the running
# state, so every MicroVM launched from the image resumes with the proxy already
# listening and the agent already imported.
#
# The heavy half — Python, LangChain Deep Agents, LangGraph, boto3 — is the agent
# container built and pushed by `infra/aws/deploy-avi.sh` from
# `backend/avi/Dockerfile`. This Dockerfile only adds the Node streaming proxy and
# starts both processes, so the MicroVM build never compiles the Python
# dependency set (it would not fit the build's time or layer budget).
#
# The base image reference is templated in by `infra/aws/deploy-avi.sh`, because
# the Lambda MicroVM image resource reads this Dockerfile from S3 and offers no
# build-arg hook. The placeholder below is replaced with the pushed ECR URI; the
# build role has `ecr:GetAuthorizationToken` plus pull permissions for it.
FROM __AVI_AGENT_IMAGE__

USER root

WORKDIR /app/microvm
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund && npm cache clean --force
COPY app.mjs ./

WORKDIR /app

# The MicroVM's ingress port. The agent itself listens on AVI_PORT (8000) on the
# loopback only, so the proxy is the single entry point.
ENV PORT=8080
EXPOSE 8080

# Lambda waits for this before snapshotting the image, so readiness is declared
# rather than raced. The proxy answers /ping from the agent's own /ping.
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD wget -qO- "http://127.0.0.1:${PORT}/ping" || exit 1

# The agent image's entrypoint starts the agent and the proxy; keep it as the
# single source of truth for process supervision.
CMD ["/usr/local/bin/avi-entrypoint"]
