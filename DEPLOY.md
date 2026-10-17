# Deploying fanfou-mcp to Vercel (remote Streamable HTTP)

Entry: `http_app:app` (pyproject `[tool.vercel] entrypoint`), Python 3.13, deps from pyproject/uv.lock.
Endpoint after deploy: `https://<project>.vercel.app/mcp` (POST, stateless, JSON). Health: `/healthz`.
Region: vercel.json asks hkg1, but deployment reported iad1 (works fine).

## Secrets (Project → Settings → Environment Variables, Production; mark Sensitive)
| name | value |
|---|---|
| FANFOU_API_KEY | your approved app's consumer key |
| FANFOU_API_SECRET | your approved app's consumer secret |
| FANFOU_OAUTH_TOKEN | user access token (single-user phase) |
| FANFOU_OAUTH_TOKEN_SECRET | user access token secret |
| FANFOU_MCP_READONLY | `1` (remote default anyway; write tools not registered) |
| MCP_AUTH_TOKEN | new random string, e.g. `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`; clients send `Authorization: Bearer <it>` |

Never set FANFOU_MCP_ALLOW_NOAUTH in production (it disables the bearer check).

### Multi-user mode (each user authorizes their own Fanfou account)
| name | value |
|---|---|
| KV_REST_API_URL | injected when a Vercel KV / Upstash Redis store is connected to the project |
| KV_REST_API_TOKEN | same (keep it secret: the store holds users' Fanfou access tokens) |
| FANFOU_MCP_PUBLIC_URL | `https://<your-project>.vercel.app` (OAuth callback base; don't rely on the Host header) |

With KV configured, FANFOU_OAUTH_TOKEN[_SECRET] and MCP_AUTH_TOKEN become optional: if set, MCP_AUTH_TOKEN
still works as an admin/owner login acting as the env account (backward compatible).

Routes:
| route | purpose |
|---|---|
| `POST /mcp` | MCP; `Authorization: Bearer <personal ffm_ token or MCP_AUTH_TOKEN>`; 401 if unknown |
| `GET /healthz`, `GET /` | health; reports `readonly` and `multi_user` |
| `GET /authorize` | gets a Fanfou request token (callback = `$FANFOU_MCP_PUBLIC_URL/callback`), 302 to fanfou.com |
| `GET /callback` | exchanges for the user's access token, issues a personal token, shows it once (HTML, no-store) |
| `POST /revoke` | deletes the caller's personal token |

KV keys: `fanfou-mcp:rt:<request_token>` (secret, EX 600, GETDEL on use) and
`fanfou-mcp:user:<sha256(personal token)>` (JSON with the user's Fanfou token + id + created_at).
Multi-user routes return 404 when no KV is configured.

To keep an existing personal setup after switching: run `dev/mint_token.py` with the KV env + your
FANFOU_OAUTH_TOKEN[_SECRET] to get a personal token, or simply go through `/authorize` once.

## Steps
1. Create project (your Vercel team), framework "Other"/Python, root = this repo.
2. Add the 5 env vars above (Production).
3. Deploy: `vercel deploy --prod` from this dir (or Git push / Vercel API). Preview URLs sit behind
   Vercel Deployment Protection, so test against the production domain.
4. Verify: `curl https://<domain>/healthz`, then
   `MCP_AUTH_TOKEN=... uv run python test_http_client.py https://<domain>/mcp`.
5. Client config (Cursor `mcp.json` / Grok Bot custom connector):
   `{"url": "https://<domain>/mcp", "headers": {"Authorization": "Bearer <MCP_AUTH_TOKEN>"}}`

## Next (not implemented)
- MCP OAuth (authorization-server metadata) so marketplace clients can connect without pasting a token.
- Rate limiting on /authorize if the instance gets abused.

## Deployed 2026-10-17 (via Vercel MCP connector)
- Your team, project `fanfou-mcp`, framework preset `python`
  (framework=null fails: `functions` pattern must be under /api). vercel.json `functions` block removed.
- Production URL: https://<your-project>.vercel.app/mcp  (health: /healthz). Runs in iad1 despite `regions: hkg1`;
  Fanfou API reachable from Vercel iad1 (no IP block observed).
- 6 env vars, Production, Sensitive. Keep a private copy of MCP_AUTH_TOKEN outside the repo.
- Redeploy: upload changed files (upload_file, sha1) + create_deployment target=production, or `vercel deploy --prod`.
