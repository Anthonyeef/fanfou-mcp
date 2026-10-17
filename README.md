# fanfou-mcp

[Model Context Protocol](https://modelcontextprotocol.io) server for **[Fanfou (饭否)](https://fanfou.com)** — let Claude、Cursor 等 MCP 客户端读写你的饭否时间线。

Two transports, same tools:

| Transport | Entry | Use |
|---|---|---|
| **stdio** | `server.py` | Local clients (Claude Desktop, Cursor, …) |
| **Streamable HTTP** | `http_app.py` | Remote hosting (e.g. Vercel), bearer-protected |

Python ≥ 3.12 · [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) (FastMCP) · Fanfou client is stdlib-only.

## Prerequisites

**You need your own approved Fanfou app key.** Fanfou has not accepted new API apps since 2020; unapproved apps can finish OAuth but every API call returns `401`.

Bring:

1. Consumer key / secret of an **approved** app
2. OAuth access token / secret for your account ([PIN flow](#oauth-pin-flow))

## Tools

**Read (11):** `verify_credentials`, `home_timeline`, `user_timeline`, `mentions`, `public_timeline`, `search_public_timeline`, `search_user_timeline`, `get_status`, `get_context`, `get_user`, `favorites`

**Write (4):** `post_status`, `delete_status`, `favorite`, `friendship`

Write tools always need `confirm=true` (otherwise they preview / refuse). Set `FANFOU_MCP_READONLY=1` to hide them entirely — **default for HTTP**; stdio defaults to allowing writes.

Responses keep useful fields only; API errors come back as `{"error": "..."}`.

## Quick start (stdio)

```bash
git clone https://github.com/Anthonyeef/fanfou-mcp.git
cd fanfou-mcp
uv sync

export FANFOU_API_KEY=...
export FANFOU_API_SECRET=...
export FANFOU_OAUTH_TOKEN=...
export FANFOU_OAUTH_TOKEN_SECRET=...

uv run python test_client.py --all
```

MCP client (`claude_desktop_config.json` / `~/.cursor/mcp.json`):

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

Or point `command` at `run.sh` and load credentials from local files (see below).

### Local HTTP

```bash
export MCP_AUTH_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
./dev_http.sh
uv run python test_http_client.py
```

## Remote HTTP (Vercel)

1. Create a **Python** Vercel project rooted at this repo (`[tool.vercel] entrypoint = "http_app:app"`).
2. Set env (Production, Sensitive): `FANFOU_API_KEY`, `FANFOU_API_SECRET`, `FANFOU_OAUTH_TOKEN`, `FANFOU_OAUTH_TOKEN_SECRET`, `MCP_AUTH_TOKEN`. Prefer `FANFOU_MCP_READONLY=1`. Never set `FANFOU_MCP_ALLOW_NOAUTH` in production.
3. Deploy, then check `GET /healthz` and `POST /mcp`.

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

Anyone with `MCP_AUTH_TOKEN` acts as your Fanfou account — treat it like a password.

More deploy notes: [DEPLOY.md](DEPLOY.md).

## Configuration

| Variable | Required | Description |
|---|---|---|
| `FANFOU_API_KEY` / `FANFOU_API_SECRET` | yes | Approved app consumer key/secret |
| `FANFOU_OAUTH_TOKEN` / `FANFOU_OAUTH_TOKEN_SECRET` | yes | User access token/secret |
| `MCP_AUTH_TOKEN` | HTTP | Bearer token for `Authorization: Bearer …` |
| `FANFOU_MCP_READONLY` | no | `1` = no write tools (stdio default `0`, HTTP default `1`) |
| `FANFOU_MCP_ALLOW_NOAUTH` | no | Local-only: allow HTTP without bearer when `MCP_AUTH_TOKEN` is unset |

Optional helpers for `run.sh` / `dev_http.sh` (env always wins): `~/.fanfou_app` + `FANFOU_APP_SECTION`, and `FANFOU_TOKEN_FILE`. Never commit these or a `.env`.

## OAuth PIN flow

Fanfou uses OAuth 1.0a out-of-band (PIN):

1. Request token: `GET https://fanfou.com/oauth/request_token` with `oauth_callback=oob`
2. Authorize in a browser: `https://fanfou.com/oauth/authorize?oauth_token=<request_token>&oauth_callback=oob` → copy the PIN
3. Exchange: `GET https://fanfou.com/oauth/access_token` with `oauth_verifier=<PIN>` → save as `FANFOU_OAUTH_TOKEN` / `FANFOU_OAUTH_TOKEN_SECRET`

**Signing quirk:** sign the **`http://`** URL, send the request over **`https://`**. Do not use a `curl/*` User-Agent (gateway returns nginx 404).

## Acknowledgements

- [Fanfou API documentation](https://github.com/FanfouAPI/FanFouAPIDoc/wiki)
- [Model Context Protocol](https://modelcontextprotocol.io) and its Python SDK

## License

[MIT](LICENSE) © Anthonyeef
