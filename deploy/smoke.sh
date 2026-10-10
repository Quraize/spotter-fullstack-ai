#!/usr/bin/env bash
# Smoke test against a running deployment: the page, the health endpoint and one real plan.
#   ./deploy/smoke.sh http://203.0.113.10
set -euo pipefail

BASE="${1:-http://127.0.0.1}"
BASE="${BASE%/}"

status() { curl -s -o /dev/null -w '%{http_code}' --max-time "${2:-10}" "$1"; }

printf 'page      %s/ ... ' "$BASE"
code=$(status "$BASE/")
[ "$code" = 200 ] || { echo "HTTP $code"; exit 1; }
curl -s --max-time 10 "$BASE/" | grep -q 'id="root"' || { echo "not the app"; exit 1; }
echo "ok"

printf 'health    %s/api/health ... ' "$BASE"
health=$(curl -s --max-time 10 "$BASE/api/health")
echo "$health" | grep -q '"status":"ok"' || { echo "unexpected: $health"; exit 1; }
echo "$health" | grep -q '"tomtom_key_configured":true' || { echo "TomTom key not configured"; exit 1; }
echo "ok"

printf 'plan      Chicago, IL -> Denver, CO (50 mi) ... '
departure=$(python3 -c 'from datetime import datetime,timedelta,timezone;print((datetime.now(timezone.utc)+timedelta(hours=3)).replace(microsecond=0).isoformat())' 2>/dev/null \
  || date -u -d '+3 hours' '+%Y-%m-%dT%H:%M:%S+00:00')
body=$(printf '{"origin":"Chicago, IL","destination":"Denver, CO","departure_time":"%s","load_weight_lb":42000,"sample_interval_miles":50}' "$departure")
start=$(date +%s)
response=$(curl -s --max-time 120 -X POST "$BASE/api/plan" -H 'Content-Type: application/json' -d "$body")
elapsed=$(( $(date +%s) - start ))
routes=$(echo "$response" | grep -o '"name":"Route [0-9]"' | wc -l | tr -d ' ')
if [ "$routes" -lt 1 ]; then
  echo "failed in ${elapsed}s: $(echo "$response" | head -c 300)"
  exit 1
fi
recommended=$(echo "$response" | grep -o '"recommended_route_id":"[^"]*"' | head -1)
echo "ok: $routes routes, $recommended, ${elapsed}s"
