"""Tiny key-value store for multi-user mode.

Production: Vercel KV / Upstash Redis over its REST API (env KV_REST_API_URL + KV_REST_API_TOKEN;
UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN are accepted too). Stdlib only, no extra deps.
Local dev: FANFOU_MCP_KV=memory gives an in-process dict (lost on restart; single process only).
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Optional


class KVError(Exception):
    pass


class UpstashKV:
    """Minimal Upstash REST client: POST <url> with a JSON command array, Bearer token."""

    def __init__(self, url: str, token: str):
        self.url, self.token = url.rstrip("/"), token

    def _cmd(self, *args):
        req = urllib.request.Request(self.url, data=json.dumps([str(a) for a in args]).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + self.token,
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                out = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise KVError("KV HTTP %s: %s" % (e.code, e.read().decode(errors="replace")[:200]))
        except urllib.error.URLError as e:
            raise KVError("KV unreachable: %s" % e.reason)
        if "error" in out:
            raise KVError("KV error: %s" % out["error"])
        return out.get("result")

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        self._cmd("SET", key, value, *(("EX", int(ttl)) if ttl else ()))

    def get(self, key: str) -> Optional[str]:
        return self._cmd("GET", key)

    def getdel(self, key: str) -> Optional[str]:
        return self._cmd("GETDEL", key)

    def delete(self, key: str):
        self._cmd("DEL", key)


class MemoryKV:
    def __init__(self):
        self._d, self._lock = {}, threading.Lock()

    def _live(self, key):
        v = self._d.get(key)
        if v and v[1] and v[1] < time.time():
            self._d.pop(key, None)
            return None
        return v

    def set(self, key, value, ttl=None):
        with self._lock:
            self._d[key] = (value, time.time() + ttl if ttl else None)

    def get(self, key):
        with self._lock:
            v = self._live(key)
            return v[0] if v else None

    def getdel(self, key):
        with self._lock:
            v = self._live(key)
            self._d.pop(key, None)
            return v[0] if v else None

    def delete(self, key):
        with self._lock:
            self._d.pop(key, None)


_store = None


def store():
    """Return the configured store, or None if multi-user storage isn't configured."""
    global _store
    if _store is None:
        url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
        tok = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        if url and tok:
            _store = UpstashKV(url, tok)
        elif os.environ.get("FANFOU_MCP_KV") == "memory":
            _store = MemoryKV()
    return _store
