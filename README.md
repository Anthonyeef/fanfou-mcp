# fanfou-mcp (box)

stdio MCP server for Fanfou. Python + mcp<2 (FastMCP), stdlib HTTP.

- Transport: https://api.fanfou.com (box blocks port 80); OAuth1 base string signed with **http://** URL (Fanfou quirk).
- api gateway returns nginx 404 for `curl/*` User-Agent; we send our own UA.
- Creds from env: FANFOU_API_KEY / FANFOU_API_SECRET / FANFOU_OAUTH_TOKEN / FANFOU_OAUTH_TOKEN_SECRET.
  `run.sh` fills unset ones from ~/.fanfou_app section `# ${FANFOU_APP_SECTION:-default}` and
  `${FANFOU_TOKEN_FILE:-~/.fanfou_token}`.

Start: `command=/path/to/fanfou-mcp/run.sh`, args=[]
(or `uv run --directory /path/to/fanfou-mcp python server.py` with env set).
Smoke test: `uv run --directory /path/to/fanfou-mcp python test_client.py [--all]`

## Status (2026-10-17)
Signature + token accepted, but every API endpoint (incl. /help/test.json) returns
401 `参数错误!` for app default (审核状态: 已驳回), over https from box AND over plain http
from a residential CN IP with the same token. request_token/access_token work.
=> app-level block; need an approved app key (and re-authorize to get a new token).

## Update (2026-10-17 12:2x)
Working with the public consumer key of default (github.com/example/client,
app/src/main/java/path/to/ClientApi.java), oob PIN authorized by your own account.
verify_credentials / home_timeline / mentions / public / search / user_timeline / favorites /
get_user / get_status / get_context all return data. Write tools untested (by design).
Re-auth helper: /workspace/fanfou_oauth.py (backup in persistent store): `req` -> open link -> `acc <PIN>`.
