"""Smoke test for the remote server: python test_http_client.py [URL] (default http://127.0.0.1:8765/mcp).
Uses MCP_AUTH_TOKEN env as bearer. Prints author + first 20 chars only."""
import asyncio, json, os, sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    url = next((a for a in sys.argv[1:] if a.startswith("http")), "http://127.0.0.1:8765/mcp")
    headers = {"Authorization": "Bearer " + os.environ["MCP_AUTH_TOKEN"]} if os.environ.get("MCP_AUTH_TOKEN") else {}
    async with streamablehttp_client(url, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print("tools:", [t.name for t in (await s.list_tools()).tools])
            for name, args in [("verify_credentials", {}), ("home_timeline", {"count": 3})]:
                res = await s.call_tool(name, args)
                sc = res.structuredContent
                if isinstance(sc, dict):
                    data = sc.get("result", sc)
                else:
                    parts = [json.loads(c.text) for c in res.content if getattr(c, "text", None)]
                    data = parts[0] if len(parts) == 1 else parts
                if isinstance(data, list):
                    for st in data[:3]: print(name, "->", st["user"]["name"], "|", st["text"][:20])
                elif "error" in data: print(name, "-> ERROR", data["error"])
                else: print(name, "->", data.get("screen_name"), data.get("id"))
asyncio.run(main())
