# Deploying fanfou-mcp to Vercel (remote Streamable HTTP)

Entry: `http_app:app` (pyproject `[tool.vercel] entrypoint`), Python 3.13, deps from pyproject/uv.lock.
Endpoint after deploy: `https://<project>.vercel.app/mcp` (POST, stateless, JSON). Health: `/healthz`.
Region: vercel.json asks hkg1, but deployment reported iad1 (works fine).

## Secrets (Project → Settings → Environment Variables, Production; mark Sensitive)
| name | value |
|---|---|
| FANFOU_API_KEY | consumer key (`# default` section of ~/.fanfou_app) |
| FANFOU_API_SECRET | consumer secret (same section) |
| FANFOU_OAUTH_TOKEN | from ~/.fanfou_token (single-user phase) |
| FANFOU_OAUTH_TOKEN_SECRET | from ~/.fanfou_token |
| FANFOU_MCP_READONLY | `1` (remote default anyway; write tools not registered) |
| MCP_AUTH_TOKEN | new random string, e.g. `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`; clients send `Authorization: Bearer <it>` |

Never set FANFOU_MCP_ALLOW_NOAUTH in production (it disables the bearer check).

## Steps
1. Create project (your Vercel team), framework "Other"/Python, root = this repo.
2. Add the 5 env vars above (Production).
3. Deploy: `vercel deploy --prod` from this dir (or Git push / Vercel API). Preview URLs sit behind
   Vercel Deployment Protection, so test against the production domain.
4. Verify: `curl https://<domain>/healthz`, then
   `MCP_AUTH_TOKEN=... uv run python test_http_client.py https://<domain>/mcp`.
5. Client config (Cursor `mcp.json` / Grok Bot custom connector):
   `{"url": "https://<domain>/mcp", "headers": {"Authorization": "Bearer <MCP_AUTH_TOKEN>"}}`

## Phase 2 (public marketplace) — not implemented
- Replace bearer check with MCP OAuth (FastMCP `auth=` / token_verifier), set `creds.current_principal` to the OAuth subject.
- Implement a `creds.TokenStore` backed by KV/Redis; add a Fanfou OAuth1 web flow (request_token → authorize with
  callback → access_token) that stores each user's token. Consumer key should then be an approved app of our own.

## Deployed 2026-10-17 (via Vercel MCP connector)
- Your team, project `fanfou-mcp`, framework preset `python`
  (framework=null fails: `functions` pattern must be under /api). vercel.json `functions` block removed.
- Production URL: https://<your-project>.vercel.app/mcp  (health: /healthz). Runs in iad1 despite `regions: hkg1`;
  Fanfou API reachable from Vercel iad1 (no IP block observed).
- 6 env vars, Production, Sensitive. MCP_AUTH_TOKEN copy on box: a private file (600, not in git).
- Redeploy: upload changed files (upload_file, sha1) + create_deployment target=production, or `vercel deploy --prod`.
