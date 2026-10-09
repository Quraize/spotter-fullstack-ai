# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest of three routes based on
forecast weather along the way, load weight, and travel time.

Built for the Spotter full-stack assessment (`docs/fs-assessment-spotter.pdf`). The investigation,
design decisions and phased plan live in `docs/PLAN.md`.

## Status

Phase 1 of 8: repository scaffold. See `docs/PLAN.md` for what each phase delivers.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework |
| Frontend | React 19, TypeScript, Vite, MapLibre GL JS |
| Routing & geocoding | TomTom Routing API (truck mode) and Geocoding API, called server-side |
| Weather | Open-Meteo hourly forecast (no key) |
| Map tiles | OpenFreeMap (no key) |

## Local development

Prerequisites: Python 3.12+, Node 22+, a TomTom API key with Routing and Geocoding enabled.

```bash
cp .env.example .env          # then fill in TOMTOM_API_KEY

# Backend (http://127.0.0.1:8000)
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py runserver

# Frontend (http://localhost:5173, proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Run backend tests from `backend/` with `pytest`.

## Repository layout

```
backend/
  config/      Django project: settings (base/dev/prod), urls, wsgi
  api/         HTTP layer: views, serializers, URL routes
  routing/     Pure domain logic: risk rules, checkpoint sampling, recommendation (Phase 2)
  providers/   TomTom and Open-Meteo clients (Phase 3)
frontend/      Vite + React + TypeScript app
deploy/        Docker Compose, nginx, deploy script (Phase 7)
docs/          Assessment PDF, plan, QA checklist, Loom script
```
