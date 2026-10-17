"""Smoke test: spawn server over stdio, list tools, call home_timeline(count=3). Prints author + first 20 chars only."""
import asyncio, json, os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    here = os.path.dirname(os.path.abspath(__file__))
    params = StdioServerParameters(command=os.path.join(here, "run.sh"), args=[], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("tools:", [t.name for t in tools.tools])
            for name, args in [("verify_credentials", {}), ("home_timeline", {"count": 3})] + ([("mentions", {"count": 1}), ("public_timeline", {"count": 1}), ("search_public_timeline", {"q": "饭否", "count": 1}), ("user_timeline", {"count": 1}), ("favorites", {"count": 1}), ("get_user", {})] if "--all" in sys.argv else []):
                res = await s.call_tool(name, args)
                sc = getattr(res, "structuredContent", None)
                if isinstance(sc, dict) and "result" in sc: data = sc["result"]
                elif sc: data = sc
                else:
                    parts = [json.loads(c.text) for c in res.content if getattr(c, "text", None)]
                    data = parts[0] if len(parts) == 1 else parts
                if isinstance(data, list):
                    for st in data[:3]: print(name, "->", st["user"]["name"], "|", st["text"][:20])
                elif isinstance(data, dict) and "error" in data: print(name, "-> ERROR", data["error"])
                else: print(name, "->", (data.get("screen_name"), data.get("id")) if isinstance(data, dict) else str(data)[:100])
asyncio.run(main())
