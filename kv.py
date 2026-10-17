"""Tiny key-value store for multi-user mode.

Production (pick one; checked in this order):
  1. Vercel KV / Upstash REST — KV_REST_API_URL + KV_REST_API_TOKEN
     (UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN also accepted). Stdlib only.
  2. Redis URL — REDIS_URL or UPSTASH_REDIS_URL (Vercel Marketplace Redis injects REDIS_URL;
     rediss:// TLS is fine). Uses the `redis` package; short-lived connections (serverless-safe).
Local: FANFOU_MCP_KV=memory → in-process dict (lost on restart; single process only).
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


class RedisKV:
    """Redis protocol client via REDIS_URL (rediss:// supported). One short-lived connection per call."""

    def __init__(self, url: str):
        self.url = url

    def _client(self):
        try:
            import redis as redis_lib
        except ImportError as e:
            raise KVError("redis package not installed (add redis to dependencies)") from e
        return redis_lib.from_url(
            self.url,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            # Single-shot: don't leave a pool spanning serverless invocations.
            max_connections=1,
        )

    def _run(self, fn):
        import redis as redis_lib
        r = self._client()
        try:
            return fn(r)
        except redis_lib.RedisError as e:
            raise KVError("Redis error: %s" % e) from e
        finally:
            try:
                r.close()
            except Exception:
                pass

    def set(self, key: str, value: str, ttl: Optional[int] = None):
        def op(r):
            if ttl:
                r.set(key, value, ex=int(ttl))
            else:
                r.set(key, value)
        self._run(op)

    def get(self, key: str) -> Optional[str]:
        return self._run(lambda r: r.get(key))

    def getdel(self, key: str) -> Optional[str]:
        def op(r):
            # GETDEL needs Redis ≥ 6.2; fall back to a GET+DEL transaction.
            if hasattr(r, "getdel"):
                try:
                    return r.getdel(key)
                except Exception:
                    pass
            pipe = r.pipeline(transaction=True)
            pipe.get(key)
            pipe.delete(key)
            val, _ = pipe.execute()
            return val
        return self._run(op)

    def delete(self, key: str):
        self._run(lambda r: r.delete(key))


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
    """Return the configured store, or None if multi-user storage isn't configured.

    RedisKV only holds the URL; each method opens and closes its own connection (serverless-safe).
    REST and memory backends are also safe to reuse across requests.
    """
    global _store
    if _store is None:
        rest_url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
        rest_tok = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
        redis_url = os.environ.get("REDIS_URL") or os.environ.get("UPSTASH_REDIS_URL")
        if rest_url and rest_tok:
            _store = UpstashKV(rest_url, rest_tok)
        elif redis_url:
            _store = RedisKV(redis_url)
        elif os.environ.get("FANFOU_MCP_KV") == "memory":
            _store = MemoryKV()
    return _store
