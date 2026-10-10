# Weather-Aware Truck Routing

A React + Django web app that helps a truck driver choose the safest of three routes based on
forecast weather along the way, load weight, and travel time.

Built for the Spotter full-stack assessment (`docs/fs-assessment-spotter.pdf`). The investigation,
design decisions and phased plan live in `docs/PLAN.md`.

## Status

Phases 0–8 complete: tested domain logic, provider clients and `POST /api/plan`; the React map UI with form, route cards, checkpoints, popups and the 0–48 h weather heatmap; hardening with a ticked QA checklist (`docs/QA.md`); a Docker Compose deployment with a one-command deploy script; and this documentation with the Loom outline in `docs/LOOM-SCRIPT.md`. See `docs/PLAN.md` for what each phase delivers.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, Django 5.2 LTS, Django REST Framework |
| Frontend | React 19, TypeScript, Vite, MapLibre GL JS |
| Routing & geocoding | TomTom Routing API (truck mode) and Geocoding API, called server-side |
| Weather | Open-Meteo hourly forecast (no key) |
| Map tiles | OpenFreeMap (no key) |

## Architecture

```
Browser: React 19 + TypeScript, MapLibre GL (route lines, checkpoint dots, heatmap layers)
   |  POST /api/plan, GET /api/health (same origin, JSON)      map tiles <-- OpenFreeMap (vector, no key)
   v
nginx (web container): serves the Vite build, proxies /api/ to backend:8000
   v
gunicorn -> Django 5.2 + DRF (backend container)
   api/        views and serializers (validation), planner (orchestration, caching, warnings, heatmap)
   routing/    pure domain logic: risk rules, checkpoint sampling, stretch aggregation, recommendation
   providers/  tomtom.py (geocoding, truck routes with timing points), openmeteo.py (hourly forecasts, batched)
      |                                        |
      v                                        v
   TomTom Geocoding + Routing API           Open-Meteo forecast API
   (cached 24 h / 1 h)                      (cached 30 min per 3 km cell)
```

One request does all the work. The planner geocodes both places, asks TomTom for three distinct truck routes
for the chosen departure, places checkpoints along each route with an ETA interpolated from TomTom's timing
points, fetches the hourly forecast once per unique checkpoint, assesses every checkpoint at its ETA, summarises
and ranks the routes, and builds the 49-hour heatmap from the same forecasts. The browser receives one JSON
document and never talks to a provider, so the TomTom key stays on the server. In development Vite proxies
`/api` to the Django dev server, so the browser sees the same single origin as in production.

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

## The map

- **Routes.** All three routes are drawn; the selected one is blue, the others grey. Clicking a route line, a checkpoint
  or a route card selects it.
- **Checkpoints** are dots coloured by the risk level at that checkpoint's ETA. Hovering shows the ETA, wind and gusts,
  rain, snow, and the rule that set the level.
- **Weather heatmap.** The shading along the corridor is the forecast risk level, for this load, at the time chosen on the
  0–48 h slider (absolute time shown, hour 0 = departure). It uses the same per-checkpoint hourly forecasts the planner
  already fetched, so moving the slider costs no network call. One MapLibre heatmap layer per risk level is drawn rather
  than one layer with a density ramp: a density ramp adds overlapping blobs together, so two nearby Moderate
  checkpoints would render as High. Per level, density saturates at that level's colour and the layers stack worst on
  top, so the shading at a checkpoint always matches its popup level at the matching hour. The slider only swaps which
  hour property the layers read, throttled to one update per animation frame. Heatmap and checkpoints can each be
  hidden.

## API

`GET /api/health` returns `{"status": "ok", "service": ..., "time": ..., "tomtom_key_configured": true}`.

`POST /api/plan` plans a trip. Request body:

```json
{
  "origin": "Chicago, IL",
  "destination": "Denver, CO",
  "departure_time": "2026-10-11T08:00:00-05:00",
  "load_weight_lb": 42000,
  "sample_interval_miles": 25
}
```

`departure_time` must carry a UTC offset and lie between 1 hour ago and 14 days ahead. `load_weight_lb` is
1 to 200,000 lb. `sample_interval_miles` is 10, 25 or 50. Response (abridged):

```json
{
  "inputs": { "origin": {"query", "name", "lat", "lon"}, "destination": {...}, "departure_time", "load_weight_lb", "sample_interval_miles" },
  "routes": [
    {
      "id": "r1", "name": "Route 1", "rank": 2, "distance_miles": 1008.4, "duration_seconds": 50040,
      "departure_time": "...", "arrival_time": "...", "traffic_delay_seconds": 120,
      "geometry": [[lon, lat], ...], "bbox": [min_lon, min_lat, max_lon, max_lat],
      "checkpoints": [
        { "index": 0, "mile": 0, "lat": ..., "lon": ..., "eta": "...",
          "wind_mph": 20.5, "gust_mph": 34.4, "rain_in_hr": 0.0, "snow_in_hr": 0.0,
          "wind_level": "low", "rain_level": "low", "snow_level": "low",
          "level": "low", "load_rule": null, "reason": "Wind 20 mph, rain 0.00 in/hr, snow 0.0 in/hr: Low" }
      ],
      "summary": { "miles_by_level": {"low", "moderate", "high", "severe", "no_travel"}, "total_miles",
                   "average_risk", "worst_level", "worst_checkpoint_index", "no_travel" }
    }
  ],
  "recommended_route_id": "r2",
  "recommendation": { "route_id": "r2", "ranked_ids": ["r2", "r3", "r1"], "reason": "...", "all_no_travel": false },
  "heatmap": { "interval_miles": 25, "hours": ["<49 ISO timestamps from departure>"],
               "points": [ { "lat", "lon", "levels": ["<49 ints, Low 0 to No Travel 4>"] } ] },
  "warnings": []
}
```

Errors are `{"error": {"code", "message", "fields"?}}`:

| Status | Code |
|---|---|
| 400 | `validation_error` (with per-field messages) |
| 422 | `geocode_not_found`, `route_not_found`, `invalid_trip`, `too_many_checkpoints` |
| 502 | `provider_bad_request` |
| 503 | `provider_unavailable`, `provider_quota_exceeded` |

**Third-party calls and caching.** Routing and geocoding use TomTom (truck mode, traffic-aware departure time,
2 alternatives requested, 4 on retry when fewer than 3 distinct routes come back). Weather uses Open-Meteo, which
counts every location in a batch against its 600 per minute and 10,000 per day free limits, so the heatmap grid is
the checkpoint set itself and forecasts are cached per 3 km cell for 30 minutes. Geocodes are cached for 24 hours
and routes for 1 hour (departure bucketed to 15 minutes). A 1,000-mile plan takes about 8 s cold and about 1.3 s
when every provider call is cached.

## Limitations

Stated rather than hidden; each one is covered by a test or a ticked check in `docs/QA.md`.

- Geocoding is US-only (`countrySet=US`); an unknown place returns `geocode_not_found` saying so, and a foreign city
  may resolve to a US namesake. The resolved names are shown above the route cards so this is visible.
- Departure must be between 1 hour ago and 14 days ahead. Open-Meteo forecasts reach 16 days, so a departure near
  the end of that window can put the last slider hours, or the last checkpoints of a long trip, past the forecast's end.
  The plan still completes using the nearest forecast hour and carries a warning that names the forecast's end time.
- One plan may use at most 500 weather locations (unique checkpoints across the three routes). Open-Meteo counts each
  location in a batch as a call against its 600 per minute limit, weighted by forecast length (16 days counts about
  1.14), so 500 locations stay under the limit for one plan. A 10-mile grid on a cross-country trip needs about 1,000
  and is refused with `too_many_checkpoints` before any quota is spent; the message says to pick a larger interval.
  Miami to Seattle works at 25 and 50 miles.
- Two long cold-cache plans within the same minute can still exceed Open-Meteo's per-minute limit; the second gets
  `provider_quota_exceeded` with the provider's "try again in one minute", and the chunks it already fetched are cached
  so the retry only asks for the rest.
- Fewer than three distinct routes (an island road, a short hop) produces as many as exist plus a warning; a single
  route is still ranked and recommended as "Only route available."
- Route timing is cached per 15-minute departure bucket to protect the TomTom quota; checkpoint ETAs always use the
  exact departure entered.
- Plans are not stored. Reloading the page clears the result, and there is no shareable link (the assessment asks
  for none).
- The map needs WebGL. Without it the form and route cards still work, but the map area stays empty.

## Assumptions

Decisions taken where the assessment leaves room, numbered as in `docs/PLAN.md` so they can be challenged one by one.

| # | Assumption |
|---|---|
| A1 | Routing is TomTom in truck mode with `departAt` set to the departure time. Load weight is not sent to the router; it drives only the PDF's risk rules. |
| A2 | The sampling interval (10, 25 or 50 miles) is the driver's choice; checkpoints sit at mile 0, N, 2N … plus the destination. |
| A3 | A checkpoint's ETA is departure plus the travel time interpolated between TomTom's timing points, so it carries the provider's traffic-aware timing. |
| A4 | Weather at a checkpoint is the forecast hour nearest to its ETA. |
| A5 | Wind thresholds use sustained wind at 10 m; gusts are shown in the popup for information only. |
| A6 | Checkpoint risk is the worst of wind, rain and snow, after the load rules are applied to the wind level. |
| A7 | A stretch between consecutive checkpoints is rated at the worse of its two endpoints; "Severe miles" and "High miles" sum stretch lengths at that level. |
| A8 | Ranking compares No Travel miles first, then the PDF's four criteria in order. A route with a No Travel checkpoint is never recommended; if all three have one, none is. |
| A9 | Average risk is the distance-weighted mean of the level index (Low 0 to No Travel 4). |
| A10 | The heatmap grid is the checkpoint set itself, with 49 hourly levels per point; weather is fetched once per unique checkpoint and cached per 3 km cell. |
| A11 | Slider hour 0 is the departure time, up to +48 h; the absolute time is shown beside the slider. |
| A12 | Every provider call goes through Django; keys stay server-side; responses are cached (geocodes 24 h, routes 1 h, weather 30 min). |
| A13 | Geocoding is limited to the US, matching the PDF's miles, inches and pounds. |
| A14 | Deployment is Docker Compose on one server, served over plain HTTP on its IP; HTTPS is added only once a domain exists. |

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

Run backend tests from `backend/` with `pytest`, and frontend tests from `frontend/` with `npm test`
(`npm run build` also type-checks, `npm run lint` runs oxlint). MapLibre needs WebGL, so the map itself is exercised
in a real headless Chromium during each phase's gate rather than in jsdom; the pure data and expression builders it
uses (`src/lib/`) are unit-tested.

Port 5173 is Vite's default; if it is taken, `npm run dev -- --port 5174`.

## Deployment

The app ships as two containers behind one port: `web` (nginx serving the built frontend and proxying `/api`
to the backend) and `backend` (gunicorn running Django with the production settings). Provider responses are
cached in a named volume shared by all gunicorn workers. Everything is in `docker-compose.yml` and `deploy/`.

Server prerequisites: Linux with Docker Engine and the compose plugin (on Ubuntu/Debian:
`curl -fsSL https://get.docker.com | sh`), `git`, port 80 reachable. No domain is needed; the app is served over
plain HTTP on the server's IP.

First deployment on the server:

```bash
git clone <repo-url> spotter && cd spotter
cp .env.example .env
# edit .env: TOMTOM_API_KEY, DJANGO_SECRET_KEY (python3 -c "import secrets; print(secrets.token_urlsafe(50))"),
#            DJANGO_ALLOWED_HOSTS=<server-ip>
./deploy/deploy.sh --no-pull
```

Every later release: `./deploy/deploy.sh` (pulls `main`, rebuilds both images, restarts the stack, runs
migrations, then runs `deploy/smoke.sh`, which loads the page, checks `/api/health` and plans a real trip).
From a laptop: `ssh user@server 'cd spotter && ./deploy/deploy.sh'`. The smoke test also works remotely:
`./deploy/smoke.sh http://<server-ip>`.

Operations: `docker compose logs -f backend` for plan timings and provider errors; `docker compose ps` for
health (both containers have healthchecks); `docker compose down` to stop. Set `WEB_PORT` in `.env` to listen on a
port other than 80. Adding HTTPS later means putting a TLS-terminating proxy (or Caddy) in front of `web` and setting
`SECURE_PROXY_SSL_HEADER` in `config/settings/prod.py`; nothing else changes.

## Repository layout

```
backend/
  config/      Django project: settings (base/dev/prod), urls, wsgi
  api/         HTTP layer: views, serializers, URL routes
  routing/     Pure domain logic: risk rules, checkpoint sampling, recommendation
  providers/   TomTom and Open-Meteo clients
frontend/      Vite + React + TypeScript app
deploy/        Dockerfiles, nginx.conf, deploy.sh, smoke.sh (docker-compose.yml is at the root)
docs/          Assessment PDF, plan, QA checklist, Loom script
```
