# Lambda MicroVM image for the agent-run streaming proxy.
#
# Lambda builds this Dockerfile, starts the server, and snapshots the running
# state. Every MicroVM launched from the image resumes from that snapshot with
# the server already listening.
FROM node:24-alpine

WORKDIR /app

# The streaming server plus the shared proxy core it imports.
COPY app.mjs ./microvm/app.mjs
COPY proxy.mjs ./proxy.mjs

ENV PORT=8080
EXPOSE 8080

# `/ready` is declared so Lambda waits for the server before snapshotting.
HEALTHCHECK --interval=5s --timeout=3s --retries=12 \
  CMD wget -qO- http://127.0.0.1:8080/ping || exit 1

CMD ["node", "microvm/app.mjs"]
