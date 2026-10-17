"""Fanfou MCP server, Streamable HTTP transport (remote / Vercel).

Routes:
  POST /mcp        MCP Streamable HTTP (stateless, JSON responses — serverless friendly)
  GET  /healthz    health / mode info (also GET /)
  GET  /authorize  multi-user: start Fanfou OAuth, redirect the browser to fanfou.com
  GET  /callback   multi-user: Fanfou redirects back here; issues a personal bearer token (HTML page)
  POST /revoke     multi-user: delete the caller's personal token (send it as Bearer)

Mode:  read-only by default (FANFOU_MCP_READONLY, default 1 here; stdio default 0).
Auth on /mcp (`Authorization: Bearer <token>`):
  - personal token (ffm_...) issued by /callback  -> acts as that Fanfou user (token looked up in KV)
  - MCP_AUTH_TOKEN (admin / owner)                -> acts as FANFOU_OAUTH_TOKEN from env (single-user, backward compatible)
  - FANFOU_MCP_ALLOW_NOAUTH=1 and no MCP_AUTH_TOKEN -> owner without auth (local dev only)
Multi-user routes are enabled when KV is configured (KV_REST_API_URL/KV_REST_API_TOKEN, or FANFOU_MCP_KV=memory).
"""
import hmac
import html
import json
import os
import urllib.parse

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

import creds
import kv
from fanfou_api import Fanfou, FanfouError, oauth_access_token, oauth_authorize_url, oauth_request_token

# Remote server is read-only unless explicitly overridden with FANFOU_MCP_READONLY=0.
os.environ.setdefault("FANFOU_MCP_READONLY", "1")
from tools import mcp, READONLY  # noqa: E402

MCP_PATH = "/mcp"


async def _send(send, status, body: bytes, ctype: str, extra_headers=()):
    headers = [(b"content-type", ctype.encode()), (b"content-length", str(len(body)).encode()), *extra_headers]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_json(send, status, obj, extra_headers=()):
    await _send(send, status, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8", extra_headers)


_HTML_HEADERS = [(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer"),
                 (b"x-frame-options", b"DENY"), (b"x-content-type-options", b"nosniff"),
                 (b"content-security-policy",
                  b"default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'")]


async def _send_html(send, status, body: str, extra_headers=()):
    await _send(send, status, body.encode(), "text/html; charset=utf-8", [*_HTML_HEADERS, *extra_headers])


def _headers(scope):
    return {k.decode().lower(): v.decode() for k, v in (scope.get("headers") or [])}


def _bearer(scope):
    auth = _headers(scope).get("authorization", "")
    return auth[7:].strip() if auth[:7].lower() == "bearer " else ""


def _base_url(scope):
    """Public origin of this service. Set FANFOU_MCP_PUBLIC_URL in production (e.g. https://<project>.vercel.app)."""
    env = os.environ.get("FANFOU_MCP_PUBLIC_URL", "").rstrip("/")
    if env:
        return env
    h = _headers(scope)
    host = h.get("x-forwarded-host") or h.get("host") or "localhost"
    proto = h.get("x-forwarded-proto") or scope.get("scheme") or "http"
    return "%s://%s" % (proto.split(",")[0].strip(), host.split(",")[0].strip())


def _query(scope):
    return dict(urllib.parse.parse_qsl(scope.get("query_string", b"").decode()))


def _multi_user():
    return kv.store() is not None


# ---------------- pages ----------------
_CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--muted:#6e6e73;--line:#e5e5ea;--code:#f5f5f7;--accent:#0071e3}
@media(prefers-color-scheme:dark){:root{--bg:#000;--fg:#f5f5f7;--muted:#a1a1a6;--line:#2c2c2e;--code:#1c1c1e;--accent:#2997ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 -apple-system,BlinkMacSystemFont,"SF Pro Text","PingFang SC","Helvetica Neue",sans-serif}
main{max-width:620px;margin:0 auto;padding:56px 24px}h1{font-size:28px;margin:0 0 8px;letter-spacing:-.01em}
p{color:var(--muted);margin:0 0 20px}h2{font-size:15px;margin:32px 0 8px}
pre{background:var(--code);border:1px solid var(--line);border-radius:10px;padding:14px;overflow-x:auto;
font:13px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-all;margin:0}
button{margin-top:8px;font:inherit;font-size:13px;border:1px solid var(--line);background:transparent;color:var(--accent);
border-radius:8px;padding:4px 12px;cursor:pointer}.warn{font-size:14px}
"""


def _page(title, inner):
    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">'
            "<title>%s · fanfou-mcp</title><style>%s</style></head><body><main>%s</main></body></html>"
            % (html.escape(title), _CSS, inner))


def _error_page(msg):
    return _page("授权失败", "<h1>授权失败</h1><p>%s</p><p><a href=\"/authorize\">重新授权</a></p>" % html.escape(msg))


def _token_page(base, bearer, screen_name):
    endpoint = base + MCP_PATH
    cfg = json.dumps({"mcpServers": {"fanfou": {"url": endpoint, "headers": {"Authorization": "Bearer " + bearer}}}},
                     indent=2, ensure_ascii=False)
    copy_js = ("<script>document.querySelectorAll('button[data-t]').forEach(function(b){b.onclick=function(){"
               "navigator.clipboard.writeText(document.getElementById(b.dataset.t).innerText);b.textContent='已复制'}})</script>")
    who = "（%s）" % html.escape(screen_name) if screen_name else ""
    return _page("授权成功", (
        "<h1>已连接饭否%s</h1>"
        "<p>这是你的个人访问令牌。它只显示这一次，请现在复制保存；任何拿到它的人都能以只读方式读取你的饭否。</p>"
        "<h2>个人令牌</h2><pre id=\"tok\">%s</pre><button data-t=\"tok\">复制</button>"
        "<h2>MCP 客户端配置</h2><pre id=\"cfg\">%s</pre><button data-t=\"cfg\">复制</button>"
        "<h2>说明</h2><p class=\"warn\">Endpoint：<code>%s</code>，请求头 <code>Authorization: Bearer &lt;令牌&gt;</code>。"
        "服务只读，不会替你发消息。令牌泄露或不再使用时，可在饭否设置里撤销对本应用的授权，"
        "或向 <code>%s/revoke</code> 发送带该令牌的 POST 请求作废它。</p>%s"
    ) % (who, html.escape(bearer), html.escape(cfg), html.escape(endpoint), html.escape(base), copy_js))


# ---------------- multi-user OAuth flow ----------------
async def _authorize(scope, send):
    try:
        app = creds.app_credentials()
        cb = _base_url(scope) + "/callback"
        rt = oauth_request_token(app.consumer_key, app.consumer_secret, cb)
        creds.save_request_token(rt["oauth_token"], rt["oauth_token_secret"])
    except (creds.CredentialError, FanfouError, kv.KVError) as e:
        print("authorize failed:", e)
        return await _send_html(send, 502, _error_page("暂时无法连接饭否，请稍后再试。"))
    loc = oauth_authorize_url(rt["oauth_token"], cb)
    await _send(send, 302, b"", "text/plain", [(b"location", loc.encode()), (b"cache-control", b"no-store")])


async def _callback(scope, send):
    q = _query(scope)
    rtok = q.get("oauth_token", "")
    if not rtok:
        return await _send_html(send, 400, _error_page("缺少 oauth_token，可能是取消了授权。"))
    try:
        secret = creds.pop_request_token(rtok)
        if not secret:
            return await _send_html(send, 400, _error_page("授权请求已过期或已使用，请重新授权。"))
        app = creds.app_credentials()
        acc = oauth_access_token(app.consumer_key, app.consumer_secret, rtok, secret, q.get("oauth_verifier") or None)
        user = creds.UserToken(acc["oauth_token"], acc["oauth_token_secret"])
        me = Fanfou(app.consumer_key, app.consumer_secret, user.token, user.token_secret).get(
            "/account/verify_credentials.json", mode="lite")
        bearer = creds.issue_personal_token(user, str(me.get("id", "")))
    except (creds.CredentialError, FanfouError, kv.KVError) as e:
        print("callback failed:", e)
        return await _send_html(send, 502, _error_page("换取饭否授权失败，请重新授权。"))
    await _send_html(send, 200, _token_page(_base_url(scope), bearer, me.get("screen_name") or me.get("name") or ""))


# ---------------- MCP auth ----------------
def _resolve_caller(scope):
    """Returns (principal, UserToken|None) or None if unauthorized. UserToken None = owner (env token)."""
    bearer = _bearer(scope)
    admin = os.environ.get("MCP_AUTH_TOKEN", "")
    if admin and bearer and hmac.compare_digest(bearer.encode(), admin.encode()):
        return "owner", None
    if bearer and _multi_user():
        rec = creds.lookup_user(bearer)  # may raise kv.KVError
        if rec:
            return "fanfou:" + rec.get("fanfou_user_id", "?"), creds.UserToken(rec["oauth_token"], rec["oauth_token_secret"])
    if not admin and not bearer and os.environ.get("FANFOU_MCP_ALLOW_NOAUTH") == "1":
        return "owner", None
    return None


_UNAUTH = [(b"www-authenticate", b'Bearer realm="fanfou-mcp"')]


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
    method = scope.get("method", "GET")
    multi = _multi_user()
    if path in ("/", "/healthz"):
        info = {"ok": True, "name": "fanfou-mcp", "mcp_endpoint": MCP_PATH, "readonly": READONLY, "multi_user": multi}
        if multi:
            info["authorize"] = "/authorize"
        return await _send_json(send, 200, info)
    if path in ("/authorize", "/callback", "/revoke") and not multi:
        return await _send_json(send, 404, {"error": "multi-user mode not enabled"})
    if path == "/authorize" and method == "GET":
        return await _authorize(scope, send)
    if path == "/callback" and method == "GET":
        return await _callback(scope, send)
    if path == "/revoke" and method == "POST":
        bearer = _bearer(scope)
        try:
            if not (bearer and creds.lookup_user(bearer)):
                return await _send_json(send, 401, {"error": "unauthorized"}, _UNAUTH)
            creds.revoke_personal_token(bearer)
        except kv.KVError as e:
            print("revoke failed:", e)
            return await _send_json(send, 503, {"error": "storage unavailable"})
        return await _send_json(send, 200, {"ok": True, "revoked": True})
    if path != MCP_PATH:
        return await _send_json(send, 404, {"error": "not found"})
    try:
        caller = _resolve_caller(scope)
    except kv.KVError as e:
        print("auth lookup failed:", e)
        return await _send_json(send, 503, {"error": "storage unavailable"})
    if caller is None:
        return await _send_json(send, 401, {"error": "unauthorized"}, _UNAUTH)
    principal, user_token = caller
    t1 = creds.current_principal.set(principal)
    t2 = creds.current_user_token.set(user_token)
    try:
        # Fresh stateless manager per request: no reliance on ASGI lifespan (Vercel-safe).
        mgr = StreamableHTTPSessionManager(app=mcp._mcp_server, stateless=True, json_response=True)
        async with mgr.run():
            await mgr.handle_request(scope, receive, send)
    finally:
        creds.current_user_token.reset(t2)
        creds.current_principal.reset(t1)
