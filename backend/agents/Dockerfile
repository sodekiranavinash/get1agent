# AgentCore Runtime container for the get1agent agent app.
# Build context is backend/ (see Makefile) so shared packages are included.
FROM --platform=linux/arm64 python:3.13-slim

# uv (copied from the official image, pinned to match the committed uv.lock).
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/packages \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies from the lockfile only (reproducible). `package = false`
# in pyproject.toml keeps uv from trying to build/install the project itself, so
# this only populates /app/.venv with the third-party deps.
COPY agents/pyproject.toml agents/uv.lock ./
RUN uv sync --frozen --no-dev

# Shared application code (bundled, not a layer — same rule as the Lambdas).
COPY packages ./packages

COPY agents/main.py ./main.py
COPY agents/agentflow ./agentflow
COPY agents/workflow ./workflow

# Run from the uv-managed virtualenv.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD ["python", "main.py"]
