#!/usr/bin/env python3
"""Single local entrypoint that routes requests to local Lambda servers.

Reads local/routes.json. Each service declares its own path `prefixes`; the
gateway builds its route table from those (longest prefix wins) — the same idea
as API Gateway routes, but local.

Usage: python3 local/gateway.py
"""
from __future__ import annotations

import http.client
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTES_FILE = os.path.join(HERE, "routes.json")

HOP_BY_HOP = {
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "proxy-connection",
    "upgrade",
    "te",
    "trailer",
}

CORS_HEADERS = {
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "authorization, content-type",
    "access-control-allow-methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
}


def load_config() -> tuple[int, list[dict[str, Any]]]:
    """Return (gateway_port, routes) derived from services[].prefixes."""
    with open(ROUTES_FILE, encoding="utf-8") as handle:
        config = json.load(handle)

    routes: list[dict[str, Any]] = []
    for service in config.get("services", []):
        for prefix in service.get("prefixes", []):
            routes.append(
                {
                    "prefix": prefix,
                    "port": service["port"],
                    "name": service.get("name", str(service["port"])),
                }
            )

    # Longest prefix first so more specific routes win.
    routes.sort(key=lambda route: len(route["prefix"]), reverse=True)
    return int(config.get("port", 9000)), routes


def match_route(routes: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    for route in routes:
        prefix = route["prefix"].rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return route
    return None


def make_handler(routes: list[dict[str, Any]]):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "get1agent-gateway/0.1"

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("content-type", content_type)
            for key, value in CORS_HEADERS.items():
                self.send_header(key, value)
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(204, b"")

        def _proxy(self) -> None:
            route = match_route(routes, self.path)
            if route is None:
                self._send(404, json.dumps({"error": f"no route for {self.path}"}).encode())
                return

            length = int(self.headers.get("content-length") or 0)
            payload = self.rfile.read(length) if length else None
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in HOP_BY_HOP
            }

            connection = http.client.HTTPConnection("localhost", route["port"], timeout=120)
            try:
                connection.request(self.command, self.path, body=payload, headers=headers)
                response = connection.getresponse()
                data = response.read()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() in HOP_BY_HOP or key.lower() in CORS_HEADERS:
                        continue
                    self.send_header(key, value)
                for key, value in CORS_HEADERS.items():
                    self.send_header(key, value)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as exc:  # noqa: BLE001
                self._send(502, json.dumps({"error": str(exc)}).encode())
            finally:
                connection.close()

        do_GET = _proxy
        do_POST = _proxy
        do_PUT = _proxy
        do_PATCH = _proxy
        do_DELETE = _proxy

        def log_message(self, fmt: str, *args: Any) -> None:
            route = match_route(routes, self.path)
            target = f"{route['name']}:{route['port']}" if route else "?"
            print(f"[gateway] {self.command} {self.path} -> {target}")

    return Handler


def main() -> int:
    port, routes = load_config()
    if not routes:
        print("No routes configured (add prefixes to local/routes.json)", file=sys.stderr)
        return 1
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(routes))
    print(f"[gateway] listening on http://localhost:{port}")
    print(
        "[gateway] routes: "
        + ", ".join(f"{r['prefix']} -> {r['name']}:{r['port']}" for r in routes)
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[gateway] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
