# Avi agent service — LangChain Deep Agents on Amazon Bedrock.
#
# A container, not a Lambda zip: the guest Lambda is deliberately kept free of the
# agent framework (see the Makefile), so the full dependency set lives only here,
# where there is no zip size ceiling.
#
# Build context is `backend/` (see ../Makefile), so the shared packages are
# available:
#   docker build -f avi/Dockerfile -t get1agent-avi backend
#
# The image hosts two processes: this service (FastAPI on 8000) and the MicroVM
# proxy (Node on 8080, the MicroVM's ingress port). Both are started by the
# entrypoint, and the proxy exits if the agent exits, so a crash is visible.
FROM --platform=linux/arm64 python:3.13-slim AS runtime

# uv (pinned to match the committed uv.lock) installs the dependencies.
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/packages \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    AVI_MODE=prod \
    AVI_PORT=8000 \
    PORT=8080

WORKDIR /app

# Dependencies first, from the lockfile only, so a code change does not refetch
# them. `package = false` keeps uv from building/installing the project itself.
COPY avi/pyproject.toml avi/uv.lock ./
RUN uv sync --frozen --no-dev

# Shared application code (bundled, not layered — the repo rule).
COPY packages ./packages

# The service itself.
COPY avi/main.py ./main.py
COPY avi/handler.py ./handler.py
COPY avi/avi ./avi

# AgentCore-style runtime is not used here (the MicroVM proxy is the ingress),
# but the same layout is kept so the service can move without a rewrite.

# --- Node proxy ---------------------------------------------------------------
# Node is copied from the official image only the once, at build time, to install
# the proxy's single dependency (`ws`). The runtime image keeps Node but not npm,
# because the proxy is a plain ESM script.
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

WORKDIR /app/microvm
COPY services/avi/microvm/package.json ./
RUN npm install --omit=dev --no-audit --no-fund && rm -rf /usr/local/lib/node_modules/npm
COPY services/avi/microvm/app.mjs ./

WORKDIR /app
COPY services/avi/entrypoint.sh /usr/local/bin/avi-entrypoint
RUN chmod +x /usr/local/bin/avi-entrypoint

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080

# The proxy is the ingress; the agent listens on the loopback only.
CMD ["/usr/local/bin/avi-entrypoint"]
