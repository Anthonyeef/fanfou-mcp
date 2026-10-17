#!/usr/bin/env bash
# Loads creds from ~/.fanfou_app (section "# default") and ~/.fanfou_token when env vars are not already set.
set -e
sec="${FANFOU_APP_SECTION:-default}"
if [ -z "$FANFOU_API_KEY" ] && [ -f "$HOME/.fanfou_app" ]; then
  eval "$(awk -v s="# $sec" '/^# /&&!/^# note/{on=index($0,s)==1} on&&/^FANFOU_API_(KEY|SECRET)=/{print "export "$0}' "$HOME/.fanfou_app")"
fi
if [ -z "$FANFOU_OAUTH_TOKEN" ] && [ -f "$HOME/.fanfou_token" ]; then
  eval "$(grep -E '^FANFOU_OAUTH_TOKEN(_SECRET)?=' "$HOME/.fanfou_token" | sed 's/^/export /')"
fi
exec uv run --quiet --directory "$(dirname "$0")" python server.py
