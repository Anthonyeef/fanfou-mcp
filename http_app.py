"""Fanfou MCP server, Streamable HTTP transport (remote / Vercel).

Endpoint: POST /mcp  (stateless, JSON responses — serverless friendly)
Health:   GET  /healthz
Mode:     read-only by default (FANFOU_MCP_READONLY, default 1 here; stdio default 0).
Auth:     `Authorization: Bearer $MCP_AUTH_TOKEN` (required unless FANFOU_MCP_ALLOW_NOAUTH=1 for local dev).
          Phase 2 will swap this for MCP OAuth (per-user principal -> creds.current_principal).
"""
import hmac
import json
import os

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

import creds

# Remote server is read-only unless explicitly overridden with FANFOU_MCP_READONLY=0.
os.environ.setdefault("FANFOU_MCP_READONLY", "1")
from tools import mcp, READONLY  # noqa: E402

MCP_PATH = "/mcp"


async def _send_json(send, status, obj, extra_headers=()):
    body = json.dumps(obj).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def _authorized(scope):
    expected = os.environ.get("MCP_AUTH_TOKEN", "")
    if not expected:
        return os.environ.get("FANFOU_MCP_ALLOW_NOAUTH") == "1"
    auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
    return auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].strip(), expected)


async def app(scope, receive, send):
    if scope["type"] == "lifespan":  # nothing to set up; session manager is per request
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif msg["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    if scope["type"] != "http":
        return
    path = scope.get("path", "").rstrip("/") or "/"
    if path in ("/", "/healthz"):
        return await _send_json(send, 200, {"ok": True, "name": "fanfou-mcp", "mcp_endpoint": MCP_PATH, "readonly": READONLY})
    if path != MCP_PATH:
        return await _send_json(send, 404, {"error": "not found"})
    if not _authorized(scope):
        return await _send_json(send, 401, {"error": "unauthorized"},
                                [(b"www-authenticate", b'Bearer realm="fanfou-mcp"')])
    # single-user phase: principal is just "owner"; phase 2 sets the OAuth subject here
    tok = creds.current_principal.set("owner")
    try:
        # Fresh stateless manager per request: no reliance on ASGI lifespan (Vercel-safe).
        mgr = StreamableHTTPSessionManager(app=mcp._mcp_server, stateless=True, json_response=True)
        async with mgr.run():
            await mgr.handle_request(scope, receive, send)
    finally:
        creds.current_principal.reset(tok)
