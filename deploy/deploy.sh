#!/usr/bin/env bash
# Deploy or update the app on the server. Run on the server from the repository root:
#   ./deploy/deploy.sh            # pull latest main, rebuild, restart, migrate, smoke-test
#   ./deploy/deploy.sh --no-pull  # deploy the checked-out tree as is
#
# Needs: Docker Engine with the compose plugin, a .env next to docker-compose.yml
# (copy .env.example and fill TOMTOM_API_KEY, DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS).
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

[ -f .env ] || { echo "Missing .env (copy .env.example and fill it in)." >&2; exit 1; }
for key in TOMTOM_API_KEY DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS; do
  value=$(grep -E "^${key}=" .env | tail -1 | cut -d= -f2- | tr -d '[:space:]')
  if [ -z "$value" ] || [ "$value" = "change-me-in-production" ]; then
    echo "$key is not set in .env" >&2; exit 1
  fi
done
secret=$(grep -E '^DJANGO_SECRET_KEY=' .env | tail -1 | cut -d= -f2- | tr -d '[:space:]')
if [ "${#secret}" -lt 50 ]; then
  echo "DJANGO_SECRET_KEY is too short (${#secret} chars); generate one with:" >&2
  echo '  python3 -c "import secrets; print(secrets.token_urlsafe(50))"' >&2
  exit 1
fi
command -v docker >/dev/null || { echo "docker is not installed" >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "the docker compose plugin is not installed" >&2; exit 1; }

if [ "$PULL" = 1 ]; then
  log "Pulling latest code"
  git pull --ff-only
fi

log "Building images"
docker compose build --pull

log "Starting services"
docker compose up -d --remove-orphans

log "Running migrations"
docker compose exec -T backend python manage.py migrate --noinput

log "Smoke test"
WEB_PORT=$(grep -E '^WEB_PORT=' .env | tail -1 | cut -d= -f2- | tr -d '[:space:]')
./deploy/smoke.sh "http://127.0.0.1:${WEB_PORT:-80}"

log "Deployed. Containers:"
docker compose ps
