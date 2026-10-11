#!/usr/bin/env bash
# Smoke test against a running deployment: the page, the health endpoint, the public host(s) Django must
# accept, and one real plan.
#   ./deploy/smoke.sh http://203.0.113.10:8080                # from anywhere
#   ./deploy/smoke.sh http://127.0.0.1:8080 203.0.113.10      # on the server: also send Host: 203.0.113.10
# The second argument is a comma-separated list of public hosts (deploy.sh passes DJANGO_ALLOWED_HOSTS);
# each is sent as the Host header so a wrong DJANGO_ALLOWED_HOSTS fails here, not in the driver's browser.
set -euo pipefail

BASE="${1:-http://127.0.0.1}"
BASE="${BASE%/}"
PUBLIC_HOSTS="${2:-}"

fail() { echo "$*"; exit 1; }
get() { curl -s --max-time "${2:-10}" "$1" || fail "no response (curl exit $?)"; }
status() { curl -s -o /dev/null -w '%{http_code}' --max-time "${2:-10}" "$1" || fail "no response (curl exit $?)"; }

printf 'page      %s/ ... ' "$BASE"
code=$(status "$BASE/")
[ "$code" = 200 ] || fail "HTTP $code"
get "$BASE/" | grep -q 'id="root"' || fail "not the app"
echo "ok"

printf 'health    %s/api/health ... ' "$BASE"
health=$(get "$BASE/api/health")
echo "$health" | grep -q '"status":"ok"' || fail "unexpected: $health"
echo "$health" | grep -q '"tomtom_key_configured":true' || fail "TomTom key not configured"
echo "ok"

for host in ${PUBLIC_HOSTS//,/ }; do
  printf 'host      Host: %s accepted ... ' "$host"
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H "Host: $host" "$BASE/api/health" || echo "000")
  [ "$code" = 200 ] || fail "HTTP $code: Django rejects Host '$host'; add the public IP or name to DJANGO_ALLOWED_HOSTS in .env"
  echo "ok"
done

printf 'plan      Chicago, IL -> Denver, CO (50 mi) ... '
departure=$(python3 -c 'from datetime import datetime,timedelta,timezone;print((datetime.now(timezone.utc)+timedelta(hours=3)).replace(microsecond=0).isoformat())' 2>/dev/null \
  || date -u -d '+3 hours' '+%Y-%m-%dT%H:%M:%S+00:00')
body=$(printf '{"origin":"Chicago, IL","destination":"Denver, CO","departure_time":"%s","load_weight_lb":42000,"sample_interval_miles":50}' "$departure")
start=$(date +%s)
response=$(curl -s --max-time 120 -X POST "$BASE/api/plan" -H 'Content-Type: application/json' -d "$body") \
  || fail "no response (curl exit $?)"
elapsed=$(( $(date +%s) - start ))
routes=$(echo "$response" | grep -o '"name":"Route [0-9]"' | wc -l | tr -d ' ' || true)
[ "${routes:-0}" -ge 1 ] || fail "failed in ${elapsed}s: $(echo "$response" | head -c 300)"
recommended=$(echo "$response" | grep -o '"recommended_route_id":"[^"]*"' | head -1 || true)
echo "ok: $routes routes, $recommended, ${elapsed}s"
