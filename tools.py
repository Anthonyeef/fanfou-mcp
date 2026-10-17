"""Fanfou MCP tools (shared by stdio `server.py` and remote `http_app.py`).
Read tools are safe; write tools need explicit user confirmation."""
from mcp.server.fastmcp import FastMCP
from fanfou_api import Fanfou, FanfouError
import creds

mcp = FastMCP("fanfou", stateless_http=True, json_response=True)
_clients = {}


def ff():
    try:
        app, tok = creds.resolve()
    except creds.CredentialError as e:
        raise FanfouError(str(e))
    key = (app.consumer_key, tok.token)
    if key not in _clients:
        _clients[key] = Fanfou(app.consumer_key, app.consumer_secret, tok.token, tok.token_secret)
    return _clients[key]


def _user(u):
    if not u:
        return None
    return {k: u.get(k) for k in ("id", "unique_id", "name", "screen_name", "location", "description",
                                  "followers_count", "friends_count", "statuses_count", "protected", "created_at")
            if k in u}


def _status(s):
    out = {k: s.get(k) for k in ("id", "rawid", "created_at", "text", "source", "favorited",
                                 "in_reply_to_status_id", "in_reply_to_screen_name", "repost_status_id") if k in s}
    u = s.get("user") or {}
    out["user"] = {"id": u.get("id"), "name": u.get("screen_name") or u.get("name")}
    if s.get("photo"):
        out["photo"] = s["photo"].get("largeurl") or s["photo"].get("url")
    if s.get("repost_status"):
        out["repost_status"] = _status(s["repost_status"])
    return out


def _call(fn):
    try:
        return fn()
    except FanfouError as e:
        return {"error": str(e)}


def _list(path, **params):
    return _call(lambda: [_status(s) for s in ff().get(path, mode="lite", **params)])


@mcp.tool()
def verify_credentials() -> dict:
    """Return the authenticated Fanfou account (read-only)."""
    return _call(lambda: _user(ff().get("/account/verify_credentials.json")))


@mcp.tool()
def home_timeline(count: int = 20, since_id: str = "", max_id: str = "", page: int = 0) -> list | dict:
    """Read the authenticated user's home timeline (statuses from people they follow). count 1-60."""
    return _list("/statuses/home_timeline.json", count=count, since_id=since_id, max_id=max_id, page=page or None)


@mcp.tool()
def user_timeline(user_id: str = "", count: int = 20, since_id: str = "", max_id: str = "", page: int = 0) -> list | dict:
    """Read a user's statuses. user_id empty = the authenticated user. count 1-60."""
    return _list("/statuses/user_timeline.json", id=user_id, count=count, since_id=since_id, max_id=max_id, page=page or None)


@mcp.tool()
def mentions(count: int = 20, since_id: str = "", max_id: str = "", page: int = 0) -> list | dict:
    """Read statuses that mention the authenticated user. count 1-60."""
    return _list("/statuses/mentions.json", count=count, since_id=since_id, max_id=max_id, page=page or None)


@mcp.tool()
def public_timeline(count: int = 20) -> list | dict:
    """Read the latest public statuses on Fanfou. count 1-60."""
    return _list("/statuses/public_timeline.json", count=count)


@mcp.tool()
def search_public_timeline(q: str, count: int = 20, max_id: str = "") -> list | dict:
    """Search public statuses by keyword (supports 'a b' AND and 'a|b' OR)."""
    return _list("/search/public_timeline.json", q=q, count=count, max_id=max_id)


@mcp.tool()
def search_user_timeline(q: str, user_id: str = "", count: int = 20, max_id: str = "") -> list | dict:
    """Search within one user's statuses (user_id empty = the authenticated user)."""
    return _list("/search/user_timeline.json", q=q, id=user_id, count=count, max_id=max_id)


@mcp.tool()
def get_status(status_id: str) -> dict:
    """Get one status by id."""
    return _call(lambda: _status(ff().get("/statuses/show.json", id=status_id, mode="lite")))


@mcp.tool()
def get_context(status_id: str) -> list | dict:
    """Get the conversation context (reply chain) of a status."""
    return _list("/statuses/context_timeline.json", id=status_id)


@mcp.tool()
def get_user(user_id: str = "") -> dict:
    """Get a user's profile by id (empty = the authenticated user)."""
    return _call(lambda: _user(ff().get("/users/show.json", id=user_id, mode="lite")))


@mcp.tool()
def favorites(user_id: str = "", count: int = 20, page: int = 0) -> list | dict:
    """Read a user's favorited statuses (empty = the authenticated user)."""
    path = "/favorites/%s.json" % user_id if user_id else "/favorites.json"
    return _list(path, count=count, page=page or None)


# ---- write tools: MUST have explicit user confirmation ----
_W = " WRITE ACTION: only call after the user has explicitly confirmed this exact action and content in chat. Requires confirm=true."


@mcp.tool(description="Post a new status (发饭). Optional in_reply_to_status_id / repost_status_id." + _W)
def post_status(status: str, in_reply_to_status_id: str = "", repost_status_id: str = "", confirm: bool = False) -> dict:
    if not confirm:
        return {"error": "not sent: confirm=true required after explicit user confirmation", "preview": status}
    return _call(lambda: _status(ff().post("/statuses/update.json", status=status,
                                           in_reply_to_status_id=in_reply_to_status_id,
                                           repost_status_id=repost_status_id, mode="lite")))


@mcp.tool(description="Delete one of the user's own statuses." + _W)
def delete_status(status_id: str, confirm: bool = False) -> dict:
    if not confirm:
        return {"error": "not deleted: confirm=true required after explicit user confirmation"}
    return _call(lambda: _status(ff().post("/statuses/destroy.json", id=status_id)))


@mcp.tool(description="Favorite (action='create') or unfavorite (action='destroy') a status." + _W)
def favorite(status_id: str, action: str = "create", confirm: bool = False) -> dict:
    if action not in ("create", "destroy"):
        return {"error": "action must be create or destroy"}
    if not confirm:
        return {"error": "not done: confirm=true required after explicit user confirmation"}
    return _call(lambda: _status(ff().post("/favorites/%s/%s.json" % (action, status_id))))


@mcp.tool(description="Follow (action='create') or unfollow (action='destroy') a user." + _W)
def friendship(user_id: str, action: str = "create", confirm: bool = False) -> dict:
    if action not in ("create", "destroy"):
        return {"error": "action must be create or destroy"}
    if not confirm:
        return {"error": "not done: confirm=true required after explicit user confirmation"}
    return _call(lambda: _user(ff().post("/friendships/%s.json" % action, id=user_id)))

