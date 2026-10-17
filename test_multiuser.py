"""Multi-user end-to-end test (local).

1. python dev/mock_upstash.py 8079 &            # or point KV_* at a real Upstash/Vercel KV
2. export KV_REST_API_URL=http://127.0.0.1:8079 KV_REST_API_TOKEN=dev
   export FANFOU_API_KEY=... FANFOU_API_SECRET=... FANFOU_OAUTH_TOKEN=... FANFOU_OAUTH_TOKEN_SECRET=...
   export MCP_AUTH_TOKEN=<random>                # admin/owner token (optional)
3. ./dev_http.sh &                               # serves http://127.0.0.1:8765
4. uv run python test_multiuser.py [http://127.0.0.1:8765]

Covers: /authorize (real Fanfou request_token + 302 + TTL'd KV key), /callback (Fanfou access_token step
simulated in-process, real verify_credentials), per-user token injection, 401s, admin token, revoke.
Prints ids and short snippets only, never tokens."""
import asyncio, json, os, re, sys
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

import creds, kv

BASE = next((a for a in sys.argv[1:] if a.startswith("http")), "http://127.0.0.1:8765").rstrip("/")
ok = True


def check(cond, msg):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + msg)


async def call(bearer, tool, args=None):
    async with streamablehttp_client(BASE + "/mcp", headers={"Authorization": "Bearer " + bearer}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            if tool == "__list__":
                return [t.name for t in (await s.list_tools()).tools]
            res = await s.call_tool(tool, args or {})
            sc = res.structuredContent
            if isinstance(sc, dict):
                return sc.get("result", sc)
            parts = [json.loads(c.text) for c in res.content if getattr(c, "text", None)]
            return parts[0] if len(parts) == 1 else parts


async def main():
    store = kv.store()
    assert store is not None, "set KV_REST_API_URL / KV_REST_API_TOKEN"
    async with httpx.AsyncClient(timeout=30) as h:
        hz = (await h.get(BASE + "/healthz")).json()
        check(hz.get("multi_user") and hz.get("readonly"), "healthz: multi_user + readonly %s" % hz)

        # /authorize: real request_token from Fanfou, redirect, TTL'd secret in KV
        r = await h.get(BASE + "/authorize", follow_redirects=False)
        loc = r.headers.get("location", "")
        m = re.search(r"oauth_token=([^&]+)", loc)
        check(r.status_code == 302 and loc.startswith("https://fanfou.com/oauth/authorize?") and m
              and "oauth_callback=" in loc, "/authorize -> 302 to fanfou.com authorize page")
        if m and hasattr(store, "_cmd"):
            ttl = store._cmd("TTL", creds.PREFIX + "rt:" + m.group(1))
            check(0 < int(ttl) <= creds.REQUEST_TOKEN_TTL, "request token secret stored with TTL (%ss)" % ttl)

        r = await h.get(BASE + "/callback?oauth_token=bogus")
        check(r.status_code == 400, "/callback with unknown/expired request token -> 400")
        r = await h.post(BASE + "/mcp", json={})
        check(r.status_code == 401, "/mcp without bearer -> 401")
        r = await h.post(BASE + "/mcp", json={}, headers={"Authorization": "Bearer ffm_" + "x" * 43})
        check(r.status_code == 401, "/mcp with unknown personal token -> 401")

    # /callback in-process: simulate Fanfou's access_token step (needs a human click in reality)
    import http_app
    real_user = creds.UserToken(os.environ["FANFOU_OAUTH_TOKEN"], os.environ["FANFOU_OAUTH_TOKEN_SECRET"])
    seen = {}

    def fake_access_token(ck, cs, rt, rts, verifier=None):
        seen.update(rt=rt, rts=rts, verifier=verifier)
        return {"oauth_token": real_user.token, "oauth_token_secret": real_user.token_secret}

    http_app.oauth_access_token = fake_access_token
    creds.save_request_token("test-rt", "test-rt-secret")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=http_app.app), base_url=BASE) as h:
        r = await h.get("/callback?oauth_token=test-rt&oauth_verifier=123")
        tok = re.search(r"ffm_[A-Za-z0-9_\-]{40,}", r.text)
        check(r.status_code == 200 and tok and seen.get("rts") == "test-rt-secret" and seen.get("verifier") == "123",
              "/callback -> access_token exchange with stored secret, page shows personal token")
        check(BASE + "/mcp" in r.text and "Authorization" in r.text, "/callback page includes MCP config snippet")
        check(r.headers.get("cache-control") == "no-store", "/callback page is no-store")
        r2 = await h.get("/callback?oauth_token=test-rt")
        check(r2.status_code == 400, "/callback replay with same request token -> 400 (one-shot)")
    user_bearer = tok.group(0)
    rec = creds.lookup_user(user_bearer)
    raw_keys = store._cmd("KEYS", "*") if hasattr(store, "_cmd") else []
    check(rec and not any(user_bearer in k for k in raw_keys), "KV record keyed by sha256(token), token not stored in clear")

    # per-user injection: a second user whose Fanfou token is bogus must NOT see the first user's data
    bogus_bearer = creds.issue_personal_token(creds.UserToken("bogus-token", "bogus-secret"), "000")
    names = await call(user_bearer, "__list__")
    check(not {"post_status", "delete_status", "favorite", "friendship"} & set(names) and "home_timeline" in names,
          "write tools not registered (%d tools)" % len(names))
    me, bad, tl = await asyncio.gather(call(user_bearer, "verify_credentials"),
                                       call(bogus_bearer, "verify_credentials"),
                                       call(user_bearer, "home_timeline", {"count": 3}))
    check(isinstance(me, dict) and str(me.get("id")) == rec["fanfou_user_id"],
          "personal token -> verify_credentials returns the authorized user (id matches KV record)")
    check(isinstance(bad, dict) and "error" in bad, "other user's token is used for their request (bogus -> %s)"
          % (bad.get("error", "")[:60] if isinstance(bad, dict) else bad))
    check(isinstance(tl, list) and tl, "personal token -> home_timeline returns %d live statuses" % len(tl or []))
    for st in (tl or [])[:3]:
        print("     ", st["created_at"][:16], "|", st["text"][:16].replace("\n", " "))

    admin = os.environ.get("MCP_AUTH_TOKEN")
    if admin:
        am = await call(admin, "verify_credentials")
        check(isinstance(am, dict) and am.get("id"), "admin MCP_AUTH_TOKEN still works (owner mode, env token)")

    async with httpx.AsyncClient(timeout=30) as h:
        for b in (user_bearer, bogus_bearer):
            r = await h.post(BASE + "/revoke", headers={"Authorization": "Bearer " + b})
            check(r.status_code == 200, "/revoke -> 200")
        r = await h.post(BASE + "/mcp", json={}, headers={"Authorization": "Bearer " + user_bearer})
        check(r.status_code == 401, "revoked token -> 401")
    print("ALL PASS" if ok else "SOME CHECKS FAILED")
    sys.exit(0 if ok else 1)


asyncio.run(main())
