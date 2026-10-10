#!/usr/bin/env bash
# Deploy or update the app on the server. Run on the server from the repository root:
#   ./deploy/deploy.sh            # pull latest main, rebuild, restart, migrate, smoke-test
#   ./deploy/deploy.sh --no-pull  # deploy the checked-out tree as is
#
# Needs: Docker Engine with the compose plugin, a .env next to docker-compose.yml
# (copy .env.example and fill TOMTOM_API_KEY, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS).
#
# Scope: every docker command here is `docker compose` against the project named in docker-compose.yml
# ("spotter-assessment"), so it can only build, start or migrate this stack's two containers. It never
# pulls shared base images, removes containers, or touches anything else running on the host, and it
# refuses to start if WEB_PORT is already served by another service.
set -euo pipefail

cd "$(dirname "$0")/.."
PULL=1
for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

log() { printf '\n==> %s\n' "$*"; }
env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '[:space:]'; }

[ -f .env ] || { echo "Missing .env (copy .env.example and fill it in)." >&2; exit 1; }
for key in TOMTOM_API_KEY DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS; do
  value=$(env_value "$key")
  if [ -z "$value" ] || [ "$value" = "change-me-in-production" ]; then
    echo "$key is not set in .env" >&2; exit 1
  fi
done
secret=$(env_value DJANGO_SECRET_KEY)
if [ "${#secret}" -lt 50 ]; then
  echo "DJANGO_SECRET_KEY is too short (${#secret} chars); generate one with:" >&2
  echo '  python3 -c "import secrets; print(secrets.token_urlsafe(50))"' >&2
  exit 1
fi
command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "the docker compose plugin is not installed" >&2; exit 1; }

WEB_PORT=$(env_value WEB_PORT)
WEB_PORT=${WEB_PORT:-80}
# The port may be busy only if it is our own web container from a previous deploy.
if command -v ss >/dev/null && [ -z "$(docker compose ps -q web 2>/dev/null)" ] \
   && [ -n "$(ss -ltnH "sport = :${WEB_PORT}" 2>/dev/null)" ]; then
  echo "Port ${WEB_PORT} is already in use by another service on this host." >&2
  echo "Set WEB_PORT in .env to a free port (for example WEB_PORT=8080) and run again." >&2
  exit 1
fi

if [ "$PULL" = 1 ]; then
  log "Pulling latest code"
  git pull --ff-only
fi

log "Building images"
docker compose build

log "Starting services"
docker compose up -d

log "Running migrations"
docker compose exec -T backend python manage.py migrate --noinput

log "Smoke test"
./deploy/smoke.sh "http://127.0.0.1:${WEB_PORT}"

log "Deployed. Containers:"
docker compose ps
