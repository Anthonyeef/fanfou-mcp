# fanfou-mcp

> A [Model Context Protocol](https://modelcontextprotocol.io) server for **[Fanfou (饭否)](https://fanfou.com)**.
> 让 Claude、Cursor 等 MCP 客户端直接读写你的饭否时间线。

`fanfou-mcp` exposes the Fanfou REST API as MCP tools so that an AI assistant can read your timeline,
search statuses, look up users and (optionally, with explicit confirmation) post, delete, favorite and follow.

It ships with two transports sharing the same tool set:

| Transport | Entry point | Typical use |
|---|---|---|
| **stdio** | `server.py` | Local MCP clients (Claude Desktop, Cursor, …) launching the server as a subprocess |
| **Streamable HTTP** | `http_app.py` (ASGI) | Remote / serverless hosting, e.g. on **Vercel**, protected by a bearer token |

Python ≥ 3.12, built on the official [`mcp` Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP).
The Fanfou client itself uses only the standard library (no `requests` / `oauthlib`).

---

## ⚠️ Before you start: you need your own Fanfou app key

**Fanfou has not accepted new API application registrations since 2020** (the developer program is
whitelist-only). 饭否自 2020 年起不再开放新应用申请，新注册的应用无法通过审核，调用 API 会返回 401。

This project therefore **does not include any consumer key**. To use it you must bring:

1. A **consumer key / secret** of a Fanfou app that has already been **approved** (审核通过), and
2. An **OAuth access token / secret** for your account, obtained with that app (see [OAuth authorization](#oauth-authorization-oob-pin)).

An app whose review status is "rejected" (已驳回) or pending will be able to complete the OAuth handshake,
but every API call (even `/help/test.json`) will fail with `401 参数错误!`.

---

## Tools

### Read-only tools (11)

| Tool | Description |
|---|---|
| `verify_credentials` | Return the authenticated account |
| `home_timeline` | Home timeline (statuses from people you follow); `count` 1–60, `since_id`, `max_id`, `page` |
| `user_timeline` | A user's statuses (`user_id` empty = yourself) |
| `mentions` | Statuses mentioning you |
| `public_timeline` | Latest public statuses |
| `search_public_timeline` | Keyword search across public statuses (`a b` = AND, `a\|b` = OR) |
| `search_user_timeline` | Keyword search within one user's statuses |
| `get_status` | One status by id |
| `get_context` | Conversation context (reply chain) of a status |
| `get_user` | A user's profile (`user_id` empty = yourself) |
| `favorites` | A user's favorited statuses |

### Write tools (4)

| Tool | Description |
|---|---|
| `post_status` | Post a status; supports `in_reply_to_status_id` and `repost_status_id` |
| `delete_status` | Delete one of your own statuses |
| `favorite` | Favorite (`action="create"`) or unfavorite (`action="destroy"`) a status |
| `friendship` | Follow (`action="create"`) or unfollow (`action="destroy"`) a user |

Safety rails for write tools:

- Every write tool requires **`confirm=true`**. Without it, nothing is sent and the tool returns an error
  (`post_status` also returns a `preview` of the text). Tool descriptions instruct the model to only set
  `confirm=true` after the user has explicitly approved the exact action in chat.
- Set **`FANFOU_MCP_READONLY=1`** to not register the write tools at all. This is the **default for the
  HTTP server** (`http_app.py`); the stdio server defaults to `0` (write tools available).

Responses are trimmed to the useful fields (id, text, author, timestamps, photo URL, repost, …) to keep
the model's context small. API errors are returned as `{"error": "..."}` rather than raised.

---

## Architecture

```
fanfou_api.py   Minimal Fanfou OAuth 1.0a client (HMAC-SHA1 signing, stdlib urllib)
creds.py        Credential resolution: app key from env + per-caller user token via a pluggable TokenStore
tools.py        FastMCP instance and all 15 tool definitions; READONLY switch
server.py       stdio entry point            ->  mcp.run()
http_app.py     Streamable HTTP ASGI app     ->  POST /mcp, GET /healthz, bearer auth
```

Helper scripts:

| File | Purpose |
|---|---|
| `run.sh` | Launch the stdio server via `uv`, optionally loading credentials from local files (see below) |
| `dev_http.sh` | Serve `http_app:app` locally with uvicorn on `127.0.0.1:${PORT:-8765}` |
| `test_client.py` | stdio smoke test: list tools, call a few read tools (`--all` for more) |
| `test_http_client.py` | HTTP smoke test against a local or remote `/mcp` endpoint |

Notes on the HTTP app:

- **Stateless, JSON responses** (`stateless_http=True`, `json_response=True`) and a fresh
  `StreamableHTTPSessionManager` per request, so it does not depend on ASGI lifespan — safe for serverless.
- `creds.current_principal` is a `ContextVar` set per request. Today every caller maps to a single
  owner account (`EnvTokenStore`); the hook exists so a multi-user deployment can plug in MCP OAuth and a
  KV-backed `TokenStore` without touching the tools.

---

## Implementation notes (Fanfou quirks)

These cost real debugging time; they are documented here so you don't have to rediscover them.

1. **OAuth 1.0a: sign `http://`, request `https://`.**
   Requests are sent to `https://api.fanfou.com/...`, but the OAuth signature **base string must use the
   `http://` URL**. Signing the https URL fails with
   `Invalid signature. Expected basestring is GET&http%3A%2F%2F...`.
   签名 base string 必须用 `http://`，实际请求走 `https://`。
2. **The API gateway rejects `curl/*` User-Agents.** `api.fanfou.com` answers an nginx `404` for any
   `curl/*` UA, so the client sends its own `User-Agent`. Keep this in mind when testing by hand with curl
   (pass `-A something-else`).
3. Requests use `mode=lite` where supported to get smaller payloads.
4. Percent-encoding follows RFC 3986 (`quote(s, safe="~")`) for both the signature and the request.

---

## Configuration

| Variable | Required | Description |
|---|---|---|
| `FANFOU_API_KEY` | yes | Consumer key of an **approved** Fanfou app |
| `FANFOU_API_SECRET` | yes | Consumer secret |
| `FANFOU_OAUTH_TOKEN` | yes | User access token |
| `FANFOU_OAUTH_TOKEN_SECRET` | yes | User access token secret |
| `MCP_AUTH_TOKEN` | HTTP only | Bearer token clients must send as `Authorization: Bearer <token>` |
| `FANFOU_MCP_READONLY` | no | `1` = don't register write tools. Default `0` for stdio, `1` for HTTP |
| `FANFOU_MCP_ALLOW_NOAUTH` | no | `1` = allow HTTP requests without bearer **when `MCP_AUTH_TOKEN` is unset**. Local dev only — never in production |

Optional convenience for `run.sh` / `dev_http.sh` (environment variables always win):

- `~/.fanfou_app` — an INI-like file with sections headed `# <app name>` containing
  `FANFOU_API_KEY=...` / `FANFOU_API_SECRET=...`; select the section with `FANFOU_APP_SECTION`.
- `FANFOU_TOKEN_FILE` — a file containing `FANFOU_OAUTH_TOKEN=...` / `FANFOU_OAUTH_TOKEN_SECRET=...` lines.

Never commit these files or a `.env` (both are git-ignored).

---

## Running locally (stdio)

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Anthonyeef/fanfou-mcp.git
cd fanfou-mcp
uv sync

export FANFOU_API_KEY=<consumer_key>
export FANFOU_API_SECRET=<consumer_secret>
export FANFOU_OAUTH_TOKEN=<access_token>
export FANFOU_OAUTH_TOKEN_SECRET=<access_token_secret>

uv run python test_client.py --all     # smoke test
```

### MCP client configuration

Claude Desktop (`claude_desktop_config.json`), Cursor (`~/.cursor/mcp.json`) and most other clients accept:

```json
{
  "mcpServers": {
    "fanfou": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/fanfou-mcp", "python", "server.py"],
      "env": {
        "FANFOU_API_KEY": "<consumer_key>",
        "FANFOU_API_SECRET": "<consumer_secret>",
        "FANFOU_OAUTH_TOKEN": "<access_token>",
        "FANFOU_OAUTH_TOKEN_SECRET": "<access_token_secret>",
        "FANFOU_MCP_READONLY": "1"
      }
    }
  }
}
```

Drop `FANFOU_MCP_READONLY` (or set it to `0`) if you want the write tools. Alternatively point `command`
at `/absolute/path/to/fanfou-mcp/run.sh` and let it load credentials from local files.

### Local HTTP server

```bash
export MCP_AUTH_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
./dev_http.sh                                   # serves http://127.0.0.1:8765/mcp
uv run python test_http_client.py               # in another shell, same env
```

---

## Remote deployment (Vercel)

`pyproject.toml` declares the ASGI entry point for Vercel's Python runtime:

```toml
[tool.vercel]
entrypoint = "http_app:app"
```

1. **Create a project** in your Vercel account/team. Framework preset: **Python** (not "Other"/null —
   with no preset Vercel expects functions under `/api`). Root directory: this repo.
2. **Add environment variables** (Production, mark as *Sensitive*):
   `FANFOU_API_KEY`, `FANFOU_API_SECRET`, `FANFOU_OAUTH_TOKEN`, `FANFOU_OAUTH_TOKEN_SECRET`,
   `MCP_AUTH_TOKEN` (a fresh random string), and optionally `FANFOU_MCP_READONLY=1`
   (already the HTTP default). **Do not** set `FANFOU_MCP_ALLOW_NOAUTH`.
3. **Deploy**: `vercel deploy --prod` from the repo, or connect the Git repository.
   Preview deployments sit behind Vercel Deployment Protection, so test against the production domain.
4. **Verify**:
   ```bash
   curl https://<your-project>.vercel.app/healthz
   MCP_AUTH_TOKEN=<token> uv run python test_http_client.py https://<your-project>.vercel.app/mcp
   ```
5. **Connect a client** that supports remote MCP servers:
   ```json
   {
     "mcpServers": {
       "fanfou": {
         "url": "https://<your-project>.vercel.app/mcp",
         "headers": { "Authorization": "Bearer <MCP_AUTH_TOKEN>" }
       }
     }
   }
   ```

Endpoints: `POST /mcp` (MCP Streamable HTTP, stateless, JSON), `GET /healthz` (returns
`{"ok": true, "readonly": ...}`). `vercel.json` requests the `hkg1` region; Vercel may still run the
function elsewhere — the Fanfou API has been reachable from US regions as well.

> **Security:** with the single-user model, anyone holding `MCP_AUTH_TOKEN` acts as your Fanfou account.
> Treat it like a password and rotate it if leaked. Keep the remote server read-only unless you need writes.

---

## OAuth authorization (oob PIN)

Fanfou uses OAuth 1.0a. For a personal setup the simplest way to get an access token is the
**out-of-band (PIN)** flow. 用 oob PIN 方式拿 access token：

1. **Request token** — signed (consumer key/secret only, empty token secret) request with
   `oauth_callback=oob`:
   ```
   GET https://fanfou.com/oauth/request_token
   ```
   Response: `oauth_token=<request_token>&oauth_token_secret=<request_token_secret>`
2. **Authorize** — open in a browser while logged in to Fanfou, and approve:
   ```
   https://fanfou.com/oauth/authorize?oauth_token=<request_token>&oauth_callback=oob
   ```
   Fanfou shows a **PIN** (verifier).
3. **Access token** — signed with the request token/secret and `oauth_verifier=<PIN>`:
   ```
   GET https://fanfou.com/oauth/access_token
   ```
   Response: `oauth_token=<access_token>&oauth_token_secret=<access_token_secret>`
   → use them as `FANFOU_OAUTH_TOKEN` / `FANFOU_OAUTH_TOKEN_SECRET`.

The same quirks apply: sign the **`http://fanfou.com/oauth/...`** URL while sending the request over
https, and don't use a `curl/*` User-Agent. A minimal standalone helper:

```python
# oauth_pin.py — usage: python oauth_pin.py   (needs FANFOU_API_KEY / FANFOU_API_SECRET in env)
import base64, hashlib, hmac, os, secrets, time, urllib.parse as up, urllib.request as ur

CK, CS = os.environ["FANFOU_API_KEY"], os.environ["FANFOU_API_SECRET"]
q = lambda s: up.quote(str(s), safe="~")

def call(path, token="", token_secret="", **extra):
    p = {"oauth_consumer_key": CK, "oauth_nonce": secrets.token_hex(8), "oauth_signature_method": "HMAC-SHA1",
         "oauth_timestamp": str(int(time.time())), "oauth_version": "1.0", **extra}
    if token:
        p["oauth_token"] = token
    norm = "&".join(f"{q(k)}={q(v)}" for k, v in sorted(p.items()))
    base = "&".join(["GET", q(f"http://fanfou.com{path}"), q(norm)])          # sign http://
    key = f"{q(CS)}&{q(token_secret)}".encode()
    p["oauth_signature"] = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    hdr = {"Authorization": "OAuth " + ", ".join(f'{k}="{q(v)}"' for k, v in p.items()),
           "User-Agent": "fanfou-mcp-oauth/0.1"}
    with ur.urlopen(ur.Request(f"https://fanfou.com{path}", headers=hdr), timeout=20) as r:  # send https://
        return dict(up.parse_qsl(r.read().decode()))

req = call("/oauth/request_token", oauth_callback="oob")
print("Open and approve:\n  https://fanfou.com/oauth/authorize?oauth_token=%s&oauth_callback=oob" % req["oauth_token"])
pin = input("PIN: ").strip()
acc = call("/oauth/access_token", req["oauth_token"], req["oauth_token_secret"], oauth_verifier=pin)
print("FANFOU_OAUTH_TOKEN=%s\nFANFOU_OAUTH_TOKEN_SECRET=%s" % (acc["oauth_token"], acc["oauth_token_secret"]))
```

Store the printed values somewhere private (a password manager, a `chmod 600` file, or your host's
secret store). You can revoke the authorization from your Fanfou account settings at any time.

---

## Roadmap

- [ ] MCP OAuth for the HTTP server (per-user principal instead of a shared bearer token)
- [ ] KV/Redis-backed `TokenStore` + web OAuth callback flow, enabling multi-user hosting
- [ ] Photo upload (`/photos/upload.json`), direct messages, follower/friend lists

Contributions are welcome — please open an issue or PR.

## Acknowledgements

- [Fanfou API documentation](https://github.com/FanfouAPI/FanFouAPIDoc/wiki)
- [Model Context Protocol](https://modelcontextprotocol.io) and its Python SDK

## License

[MIT](LICENSE) © Anthonyeef
