"""Credential resolution.

App credentials (consumer key/secret) always come from env (deployment secrets).

The user's OAuth token is resolved per request:
- Multi-user (hosted) mode: the HTTP auth layer looks up the caller's personal bearer token in KV
  (see `lookup_user`) and puts that user's Fanfou token into `current_user_token` for the request.
- Owner / single-user mode (stdio, or the admin `MCP_AUTH_TOKEN` over HTTP): falls back to `token_store`,
  which reads FANFOU_OAUTH_TOKEN[_SECRET] from env.
"""
import contextvars
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Protocol

import kv


@dataclass(frozen=True)
class AppCredentials:
    consumer_key: str
    consumer_secret: str


@dataclass(frozen=True)
class UserToken:
    token: str
    token_secret: str


class CredentialError(Exception):
    pass


# Set by the HTTP auth layer for each request (who is calling). None for stdio / single-user.
current_principal: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_principal", default=None)
# Set by the HTTP auth layer in multi-user mode: the calling user's Fanfou token. Wins over token_store.
current_user_token: contextvars.ContextVar[Optional[UserToken]] = contextvars.ContextVar("current_user_token", default=None)


class TokenStore(Protocol):
    def get(self, principal: Optional[str]) -> UserToken: ...


class EnvTokenStore:
    """Owner mode: acts as the one account in FANFOU_OAUTH_TOKEN[_SECRET]."""

    def get(self, principal: Optional[str]) -> UserToken:
        t, s = os.environ.get("FANFOU_OAUTH_TOKEN", ""), os.environ.get("FANFOU_OAUTH_TOKEN_SECRET", "")
        if not (t and s):
            raise CredentialError("missing env: FANFOU_OAUTH_TOKEN / FANFOU_OAUTH_TOKEN_SECRET")
        return UserToken(t, s)


token_store: TokenStore = EnvTokenStore()


def app_credentials() -> AppCredentials:
    k, s = os.environ.get("FANFOU_API_KEY", ""), os.environ.get("FANFOU_API_SECRET", "")
    if not (k and s):
        raise CredentialError("missing env: FANFOU_API_KEY / FANFOU_API_SECRET")
    return AppCredentials(k, s)


def resolve():
    """Return (AppCredentials, UserToken) for the current request."""
    user = current_user_token.get()
    return app_credentials(), user or token_store.get(current_principal.get())


# ---------------- multi-user storage (KV) ----------------
# Keys:
#   fanfou-mcp:rt:<request_token>         -> request_token_secret            (TTL REQUEST_TOKEN_TTL)
#   fanfou-mcp:user:<sha256(bearer)>      -> {"oauth_token", "oauth_token_secret", "fanfou_user_id", "created_at"}
# Personal bearer tokens are never stored in clear: only their SHA-256 is used as the key.
PREFIX = "fanfou-mcp:"
REQUEST_TOKEN_TTL = 600
BEARER_PREFIX = "ffm_"


def _kv():
    s = kv.store()
    if s is None:
        raise CredentialError("multi-user storage not configured (set KV_REST_API_URL / KV_REST_API_TOKEN)")
    return s


def _user_key(bearer: str) -> str:
    return PREFIX + "user:" + hashlib.sha256(bearer.encode()).hexdigest()


def save_request_token(request_token: str, request_token_secret: str):
    _kv().set(PREFIX + "rt:" + request_token, request_token_secret, ttl=REQUEST_TOKEN_TTL)


def pop_request_token(request_token: str) -> Optional[str]:
    """One-shot: returns the secret and deletes it (a callback can't be replayed)."""
    return _kv().getdel(PREFIX + "rt:" + request_token)


def issue_personal_token(user: UserToken, fanfou_user_id: str) -> str:
    bearer = BEARER_PREFIX + secrets.token_urlsafe(32)  # 256 bits of entropy
    rec = {"oauth_token": user.token, "oauth_token_secret": user.token_secret,
           "fanfou_user_id": fanfou_user_id, "created_at": int(time.time())}
    _kv().set(_user_key(bearer), json.dumps(rec))
    return bearer


def lookup_user(bearer: str) -> Optional[dict]:
    if not bearer.startswith(BEARER_PREFIX):
        return None
    raw = _kv().get(_user_key(bearer))
    return json.loads(raw) if raw else None


def revoke_personal_token(bearer: str):
    _kv().delete(_user_key(bearer))
