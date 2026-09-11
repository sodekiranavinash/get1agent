#!/usr/bin/env python3
"""Minimal local HTTP runner for Lambda handlers (no SAM / no AWS / no layers).

Translates HTTP requests into Lambda events and invokes the handler in-process.

Usage:
    python local/run_lambda.py <account-settings|migration-runner|health-check>
"""
from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LAMBDAS: dict[str, dict[str, Any]] = {
    "account-settings": {
        "handler": "backend/account-settings/src/handler.py",
        "mode": "http",
        "port": 9001,
    },
    "health-check": {
        "handler": "backend/health-check/src/handler.py",
        "mode": "direct",
        "port": 9003,
    },
    "knowledge-bases": {
        "handler": "backend/knowledge-bases/src/handler.py",
        "mode": "http",
        "port": 9004,
    },
}


def load_handler(path: str) -> Callable[[dict, Any], dict]:
    spec = importlib.util.spec_from_file_location("local_lambda_handler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load handler at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["local_lambda_handler"] = module
    spec.loader.exec_module(module)
    return module.lambda_handler


def decode_claims(auth_header: str | None) -> dict | None:
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def build_http_event(method: str, path: str, headers: dict[str, str], body: str) -> dict:
    claims = decode_claims(headers.get("authorization"))
    path_only, _, query = path.partition("?")
    event: dict[str, Any] = {
        "version": "2.0",
        "rawPath": path_only,
        "rawQueryString": query,
        "headers": {key.lower(): value for key, value in headers.items()},
        "requestContext": {"http": {"method": method, "path": path_only}},
        "body": body or None,
        "isBase64Encoded": False,
    }
    if claims:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": claims}}
    return event


def make_server(name: str, lambda_handler: Callable[[dict, Any], dict], mode: str, port: int):
    class Handler(BaseHTTPRequestHandler):
        server_version = "get1agent-local/0.1"

        def _cors(self) -> None:
            self.send_header("access-control-allow-origin", "*")
            self.send_header("access-control-allow-headers", "authorization, content-type")
            self.send_header(
                "access-control-allow-methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._cors()
            self.end_headers()

        def _handle(self) -> None:
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else ""

            try:
                if mode == "http":
                    event = build_http_event(self.command, self.path, dict(self.headers), raw)
                else:
                    event = json.loads(raw) if raw else {}
                result = lambda_handler(event, None)
                status = int(result.get("statusCode", 200))
                payload = result.get("body", "") or ""
                headers = result.get("headers") or {}
            except Exception as exc:  # noqa: BLE001
                print(f"[{name}] unhandled error: {exc!r}", file=sys.stderr)
                traceback.print_exc()
                status = 500
                payload = json.dumps({"error": str(exc)})
                headers = {"content-type": "application/json"}

            body = payload if isinstance(payload, str) else json.dumps(payload)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self._cors()
            self.send_header("content-length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_PATCH = _handle
        do_DELETE = _handle

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[{name}] {self.command} {self.path}")

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in LAMBDAS:
        print(f"usage: python local/run_lambda.py <{'|'.join(LAMBDAS)}>", file=sys.stderr)
        return 2

    name = sys.argv[1]
    config = LAMBDAS[name]
    port = int(os.environ.get("PORT", config["port"]))
    handler = load_handler(os.path.join(ROOT, config["handler"]))
    server = make_server(name, handler, config["mode"], port)

    print(f"[{name}] listening on http://localhost:{port} (mode={config['mode']})")
    print(f"[{name}] DATABASE_URL={'set' if os.environ.get('DATABASE_URL') else 'NOT set'}")
    bucket = os.environ.get("S3_BUCKET")
    print(
        f"[{name}] storage={'s3://' + bucket if bucket else 'local disk (S3_BUCKET unset)'}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{name}] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
