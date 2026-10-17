#!/usr/bin/env bash
# Fanfou MCP (stdio). Credentials: env vars win; otherwise loaded from
#   ~/.fanfou_app section "# ${FANFOU_APP_SECTION:-default}"  -> FANFOU_API_KEY / FANFOU_API_SECRET
#   ${FANFOU_TOKEN_FILE:-~/.fanfou_token}               -> FANFOU_OAUTH_TOKEN / FANFOU_OAUTH_TOKEN_SECRET
# (Old rejected app: FANFOU_APP_SECTION=default FANFOU_TOKEN_FILE=~/.fanfou_token)
set -e
sec="${FANFOU_APP_SECTION:-default}"
tokfile="${FANFOU_TOKEN_FILE:-$HOME/.fanfou_token}"
if [ -z "$FANFOU_API_KEY" ] && [ -f "$HOME/.fanfou_app" ]; then
  eval "$(awk -v s="# $sec" '/^# /&&!/^# note/{on=($0==s)} on&&/^FANFOU_API_(KEY|SECRET)=/{print "export "$0}' "$HOME/.fanfou_app")"
fi
if [ -z "$FANFOU_OAUTH_TOKEN" ] && [ -f "$tokfile" ]; then
  eval "$(grep -E '^FANFOU_OAUTH_TOKEN(_SECRET)?=' "$tokfile" | sed 's/^/export /')"
fi
exec uv run --quiet --directory "$(dirname "$(readlink -f "$0")")" python server.py
