#!/usr/bin/env bash
# Local dev: load creds like run.sh, then serve http_app on 127.0.0.1:${PORT:-8765}
set -e
sec="${FANFOU_APP_SECTION:-default}"; tokfile="${FANFOU_TOKEN_FILE:-$HOME/.fanfou_token}"
[ -z "$FANFOU_API_KEY" ] && [ -f "$HOME/.fanfou_app" ] && eval "$(awk -v s="# $sec" '/^# /&&!/^# note/{on=($0==s)} on&&/^FANFOU_API_(KEY|SECRET)=/{print "export "$0}' "$HOME/.fanfou_app")"
[ -z "$FANFOU_OAUTH_TOKEN" ] && [ -f "$tokfile" ] && eval "$(grep -E '^FANFOU_OAUTH_TOKEN(_SECRET)?=' "$tokfile" | sed 's/^/export /')"
cd "$(dirname "$(readlink -f "$0")")"
exec uv run --quiet uvicorn http_app:app --host 127.0.0.1 --port "${PORT:-8765}"
