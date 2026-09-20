#!/usr/bin/env python3
"""Loopback forwarder for OAuth callbacks during local development.

Floci only serves the HTTP API on the ``get1agent.execute-api.localhost.floci.io``
host, and OAuth providers (Linear, GitHub, …) reject plaintext-HTTP redirect URIs
unless they are a loopback address (``localhost`` / ``127.0.0.1``).

This tiny stdlib proxy listens on a loopback port, rewrites the ``Host`` header
to the Floci execute-api host, and forwards to Floci on ``127.0.0.1:4566``. Point
the provider's redirect URI at the loopback URL and set:

    MCP_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/v1/mcp/oauth/callback

The provider's redirect then lands here, is proxied to Floci, and Floci's own
302 back to the SPA (FRONTEND_URL/mcp/callback) is passed straight through.

Usage:
    python3 infra/local/floci/oauth-loopback.py [--port 8765]
"""

from __future__ import annotations

import argparse
import http.client
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FLOCI_HOST = "127.0.0.1"
FLOCI_PORT = 4566
FLOCI_HTTP_HOST = "get1agent.execute-api.localhost.floci.io"
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
              "te", "trailers", "transfer-encoding", "upgrade"}


class Forwarder(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[oauth-loopback] {fmt % args}", flush=True)

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP and key.lower() != "host"
        }
        headers["Host"] = FLOCI_HTTP_HOST

        try:
            conn = http.client.HTTPConnection(FLOCI_HOST, FLOCI_PORT, timeout=60)
            conn.request(self.command, self.path, body=body, headers=headers)
            upstream = conn.getresponse()
            payload = upstream.read()
        except OSError as exc:
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            message = f"Floci unreachable: {exc}\n".encode()
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)
            return

        self.send_response(upstream.status)
        for key, value in upstream.getheaders():
            if key.lower() in HOP_BY_HOP or key.lower() == "content-length":
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = _proxy


def main() -> int:
    parser = argparse.ArgumentParser(description="Loopback OAuth callback forwarder for Floci")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Forwarder)
    print(f"[oauth-loopback] http://127.0.0.1:{args.port} -> http://{FLOCI_HTTP_HOST}:{FLOCI_PORT}")
    print(f"[oauth-loopback] set MCP_OAUTH_REDIRECT_URI=http://127.0.0.1:{args.port}/v1/mcp/oauth/callback")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        if exc.errno == 48:  # EADDRINUSE
            print(
                "[oauth-loopback] port already in use — a forwarder is likely already "
                "running. Nothing to do; use it, or stop the other one first.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        raise
