# fanfou-mcp

[中文](README.zh-CN.md) · [English](README.md)

[Model Context Protocol](https://modelcontextprotocol.io) 服务，对接 **[饭否 (Fanfou)](https://fanfou.com)** —— 让 Claude、Cursor 等 MCP 客户端读写你的饭否时间线。

两种传输共用同一套工具：

| 传输 | 入口 | 用途 |
|---|---|---|
| **stdio** | `server.py` | 本地客户端（Claude Desktop、Cursor 等） |
| **Streamable HTTP** | `http_app.py` | 远程托管（如 Vercel），Bearer 鉴权 |

Python ≥ 3.12 · [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)（FastMCP）· 饭否客户端仅用标准库。

## 前置条件

**你需要自己已审核通过的饭否应用 Key。** 饭否自 2020 年起不再接受新应用申请；未通过审核的应用可以完成 OAuth，但调用 API 会返回 `401`。

你需要准备：

1. 已**审核通过**应用的 Consumer Key / Secret
2. 该应用下你的 OAuth Access Token / Secret（见 [OAuth PIN 流程](#oauth-pin-流程)）

## 工具

**只读（11）：** `verify_credentials`、`home_timeline`、`user_timeline`、`mentions`、`public_timeline`、`search_public_timeline`、`search_user_timeline`、`get_status`、`get_context`、`get_user`、`favorites`

**写入（4）：** `post_status`、`delete_status`、`favorite`、`friendship`

写入工具必须带 `confirm=true`（否则只会预览 / 拒绝）。设置 `FANFOU_MCP_READONLY=1` 可完全隐藏写入工具 —— **HTTP 默认如此**；stdio 默认允许写入。

返回结果只保留有用字段；API 错误以 `{"error": "..."}` 形式返回。

## 快速开始（stdio）

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

MCP 客户端配置（`claude_desktop_config.json` / `~/.cursor/mcp.json`）：

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

也可以把 `command` 指到 `run.sh`，从本地文件加载凭证（见下文）。

### 本地 HTTP

```bash
export MCP_AUTH_TOKEN=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
./dev_http.sh
uv run python test_http_client.py
```

## 远程 HTTP（Vercel）

1. 在 Vercel 创建 **Python** 项目，根目录为本仓库（`[tool.vercel] entrypoint = "http_app:app"`）。
2. 配置环境变量（Production，Sensitive）：`FANFOU_API_KEY`、`FANFOU_API_SECRET`、`FANFOU_OAUTH_TOKEN`、`FANFOU_OAUTH_TOKEN_SECRET`、`MCP_AUTH_TOKEN`。建议 `FANFOU_MCP_READONLY=1`。生产环境不要设置 `FANFOU_MCP_ALLOW_NOAUTH`。
3. 部署后检查 `GET /healthz` 与 `POST /mcp`。

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

持有 `MCP_AUTH_TOKEN` 的人可以以你的饭否账号操作 —— 请当作密码保管。

更多部署说明见 [DEPLOY.md](DEPLOY.md)。

## 配置

| 变量 | 必填 | 说明 |
|---|---|---|
| `FANFOU_API_KEY` / `FANFOU_API_SECRET` | 是 | 已通过审核应用的 Consumer Key/Secret |
| `FANFOU_OAUTH_TOKEN` / `FANFOU_OAUTH_TOKEN_SECRET` | 是 | 用户 Access Token/Secret |
| `MCP_AUTH_TOKEN` | HTTP | `Authorization: Bearer …` 所用 Bearer |
| `FANFOU_MCP_READONLY` | 否 | `1` = 不注册写入工具（stdio 默认 `0`，HTTP 默认 `1`） |
| `FANFOU_MCP_ALLOW_NOAUTH` | 否 | 仅本地：未设置 `MCP_AUTH_TOKEN` 时允许无 Bearer 访问 |

`run.sh` / `dev_http.sh` 可选从文件加载（环境变量优先）：`~/.fanfou_app` + `FANFOU_APP_SECTION`，以及 `FANFOU_TOKEN_FILE`。不要提交这些文件或 `.env`。

## OAuth PIN 流程

饭否使用 OAuth 1.0a 的 out-of-band（PIN）方式：

1. 申请 Request Token：`GET https://fanfou.com/oauth/request_token`，带 `oauth_callback=oob`
2. 浏览器授权：`https://fanfou.com/oauth/authorize?oauth_token=<request_token>&oauth_callback=oob` → 记下 PIN
3. 换取 Access Token：`GET https://fanfou.com/oauth/access_token`，带 `oauth_verifier=<PIN>` → 保存为 `FANFOU_OAUTH_TOKEN` / `FANFOU_OAUTH_TOKEN_SECRET`

**签名注意：** 签名用 **`http://`** URL，实际请求走 **`https://`**。不要使用 `curl/*` User-Agent（网关会返回 nginx 404）。

## 致谢

- [饭否 API 文档](https://github.com/FanfouAPI/FanFouAPIDoc/wiki)
- [Model Context Protocol](https://modelcontextprotocol.io) 及其 Python SDK

## 许可证

[MIT](LICENSE) © Anthonyeef
