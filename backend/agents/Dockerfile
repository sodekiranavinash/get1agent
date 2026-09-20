# AgentCore Runtime container for the get1agent agent app.
# Build context is backend/ (see Makefile) so shared packages are included.
FROM --platform=linux/arm64 python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app:/app/packages

WORKDIR /app

COPY agents/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Shared application code (bundled, not a layer — same rule as the Lambdas).
COPY packages ./packages

COPY agents/main.py ./main.py
COPY agents/agentflow ./agentflow

EXPOSE 8080

CMD ["python", "main.py"]
