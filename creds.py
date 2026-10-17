"""Credential resolution.

Phase 1 (now, self-hosted): consumer key/secret AND the user's OAuth token come from env vars
(deployment secrets). Phase 2 (public plugin): consumer key/secret stay in env, the user's token
is looked up per authenticated MCP caller (e.g. after an OAuth flow) via a TokenStore keyed by
`current_principal`, which the HTTP auth layer sets per request.
"""
import contextvars
import os
from dataclasses import dataclass
from typing import Optional, Protocol


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


class TokenStore(Protocol):
    def get(self, principal: Optional[str]) -> UserToken: ...


class EnvTokenStore:
    """Single-user mode: every caller acts as the one account in FANFOU_OAUTH_TOKEN[_SECRET]."""

    def get(self, principal: Optional[str]) -> UserToken:
        t, s = os.environ.get("FANFOU_OAUTH_TOKEN", ""), os.environ.get("FANFOU_OAUTH_TOKEN_SECRET", "")
        if not (t and s):
            raise CredentialError("missing env: FANFOU_OAUTH_TOKEN / FANFOU_OAUTH_TOKEN_SECRET")
        return UserToken(t, s)


# Phase 2: replace with e.g. a KV/Redis-backed store filled by an OAuth callback.
token_store: TokenStore = EnvTokenStore()


def app_credentials() -> AppCredentials:
    k, s = os.environ.get("FANFOU_API_KEY", ""), os.environ.get("FANFOU_API_SECRET", "")
    if not (k and s):
        raise CredentialError("missing env: FANFOU_API_KEY / FANFOU_API_SECRET")
    return AppCredentials(k, s)


def resolve():
    """Return (AppCredentials, UserToken) for the current request."""
    return app_credentials(), token_store.get(current_principal.get())
