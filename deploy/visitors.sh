#!/usr/bin/env bash
# Who has used the deployed app? One line per client IP from nginx's access log:
#   requests, "app" = loads of the page bundle (/assets/, only a real browser does that), trips planned
#   (POST /api/plan), 404 probes (scanners), first and last request (UTC), and the browser.
#
#   ./deploy/visitors.sh                        # on the server: the running web container's log volume
#   ./deploy/visitors.sh saved.log [more.log]   # saved copies instead, e.g. a `docker compose logs` dump
#                                               # taken before a deploy; several files are added together
#
# Read-only. The only docker command is `docker compose exec web cat`, scoped to this stack; the smoke
# test's own curl requests are left out.
set -euo pipefail

read_logs() {
  if [ "$#" -eq 0 ]; then
    cd "$(dirname "$0")/.."
    docker compose exec -T web cat /var/log/spotter/access.log
  else
    for file in "$@"; do
      [ -f "$file" ] || { echo "no such log file: $file" >&2; exit 1; }
      cat "$file"
    done
  fi
}

read_logs "$@" \
  | { grep -E '^[0-9a-f.:]+ - - \[' || true; } \
  | { grep -v '"curl/' || true; } \
  | awk '{
      ip = $1; t = substr($4, 2)
      n[ip]++
      if (!(ip in first)) first[ip] = t
      last[ip] = t
      if ($0 ~ /POST \/api\/plan/) plans[ip]++
      if ($0 ~ /GET \/assets\//) app[ip]++
      if ($9 == 404) notfound[ip]++
      split($0, q, "\""); agent[ip] = q[6]
    }
    END {
      for (ip in n)
        printf "%-15s %4d req %3d app %3d plans %3d 404s  %s .. %s  %s\n",
          ip, n[ip], app[ip] + 0, plans[ip] + 0, notfound[ip] + 0, first[ip], last[ip], substr(agent[ip], 1, 60)
    }' \
  | sort -k2 -rn
