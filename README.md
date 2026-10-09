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

## How risk and the recommendation are computed

All of this lives in `backend/routing/` as pure Python with no network or Django dependency, and is
covered by unit tests at every threshold boundary (`pytest` from `backend/`).

**Checkpoints.** Each route's geometry is walked with great-circle distances and a checkpoint is placed
every 10, 25 or 50 miles (the driver's choice) plus one at the destination. The ETA at a checkpoint is
interpolated between the routing provider's own timing points, so it reflects the provider's traffic-aware
travel time for the chosen departure.

**Weather at a checkpoint** is the hourly forecast nearest to that checkpoint's ETA: sustained wind at
10 m (mph), rain (inches in the preceding hour) and snowfall (inches in the preceding hour).

**Risk level per checkpoint** uses the PDF's thresholds:

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain (in/hr) | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules then escalate the wind level: wind of 45–54 mph with a load over 30,000 lb is No Travel, and
wind of 35–44 mph with a load over 40,000 lb is Severe. Wind of 55 mph or more is No Travel for any load.
The checkpoint's level is the worst of wind (after load rules), rain and snow.

Boundary convention: a value on a shared band boundary takes the higher band (0.25 in/hr of rain is High).
Where the PDF states an operator it is followed literally, so exactly 1.00 in/hr of rain or 3.0 in/hr of
snow is Severe and only values above those are No Travel.

**Route totals.** Each stretch between two consecutive checkpoints is rated at the worse of its two
endpoints. "Severe miles" is the total length of stretches rated Severe, likewise for every level.
Average risk is the distance-weighted mean of the level values (Low 0 to No Travel 4).

**Recommendation** follows the PDF's order: fewest Severe miles, then fewest High miles, then lowest
average risk, then shortest travel time. Because No Travel is the top of the PDF's scale, routes are
compared on No Travel miles before those four criteria, and a route with any No Travel checkpoint is never
recommended. If every route has No Travel conditions the app says so and recommends none. Miles are
compared at 0.1-mile precision and average risk at 0.01 so floating-point noise never decides a tie.

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
