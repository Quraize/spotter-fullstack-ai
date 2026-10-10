# Django API served by gunicorn. Build context: the repository root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_CACHE_DIR=/var/cache/spotter

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Unprivileged runtime user; the cache directory is a volume shared by all workers.
RUN useradd --system --create-home app \
    && mkdir -p /var/cache/spotter \
    && chown -R app:app /app /var/cache/spotter
USER app

EXPOSE 8000

# No curl in the slim image: use the interpreter for the healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

# A plan can take ~20 s on a cold cache (provider latency), so the worker timeout is generous.
# Threads, not only processes: the work is network-bound and the file cache is shared.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--threads", "4", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--error-logfile", "-"]
