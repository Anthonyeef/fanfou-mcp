# fanfou-mcp (box)

stdio MCP server for Fanfou. Python + mcp<2 (FastMCP), stdlib HTTP.

- Transport: https://api.fanfou.com (box blocks port 80); OAuth1 base string signed with **http://** URL (Fanfou quirk).
- api gateway returns nginx 404 for `curl/*` User-Agent; we send our own UA.
- Creds from env: FANFOU_API_KEY / FANFOU_API_SECRET / FANFOU_OAUTH_TOKEN / FANFOU_OAUTH_TOKEN_SECRET.
  `run.sh` fills them from ~/.fanfou_app (section `# default`, override with FANFOU_APP_SECTION) and ~/.fanfou_token if unset.

Start: `command=/path/to/fanfou-mcp/run.sh`, args=[]
(or `uv run --directory /path/to/fanfou-mcp python server.py` with env set).
Smoke test: `uv run --directory /path/to/fanfou-mcp python test_client.py`

## Status (2026-10-17)
Signature + token accepted, but every API endpoint (incl. /help/test.json) returns
401 `参数错误!` for app default (审核状态: 已驳回), over https from box AND over plain http
from a residential CN IP with the same token. request_token/access_token work.
=> app-level block; need an approved app key (and re-authorize to get a new token).
