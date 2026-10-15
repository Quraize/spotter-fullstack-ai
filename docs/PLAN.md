# Weather-Aware Truck Routing — Investigation & Phased Plan

Source of truth: `docs/fs-assessment-spotter.pdf`. Guiding rule from the PDF:
**"Prioritize correctness and clarity over extra features."** Every phase below maps to a
PDF requirement; anything not in the PDF is marked *optional* and comes last.

Plan written 2026-10-09.

---

## 1. Investigation results (verified 2026-10-09)

### 1.1 Routing API (needs: 3 route options, geometry, per-checkpoint ETA)

| Provider | 3 routes on long-haul? | Truck mode | Free tier | Card? | Verdict |
|---|---|---|---|---|---|
| **TomTom Routing API** | `maxAlternatives` 0–5 ("fewer may be returned") | yes (`travelMode=truck`, `vehicleWeight` kg) | 20K req/month, 20K geocoding/month | no | **Primary choice** (live test pending API key) |
| OpenRouteService | **No**: `maximum_distance_alternative_routes` default = 100 km | yes (`driving-hgv`) | 2,000/day | no | Rejected (long-haul alternatives impossible) |
| OSRM public demo | Live test: **2 routes** for Chicago→Denver and NYC→Philadelphia | no | demo, no SLA | no | Rejected |
| Valhalla public (FOSSGIS) | Live test: 1 alternate Chicago→Denver, **0** NYC→Philadelphia | yes | demo, no SLA | no | Rejected |
| Mapbox Directions | up to 2 alternatives (3 total), "not in all circumstances" | no | 100K/month | conflicting reports | Fallback if user has account |
| Google Routes API | up to 3 alternatives, no intermediates | no | per-SKU free quota | **yes** (billing acct) | Fallback if user has account |
| HERE Routing v8 | `alternatives` param, truck + grossWeight | yes | unclear (1,000/day "Limited" plan reported) | unclear | Not pursued |

Key TomTom facts (official docs):
- `legs[].points` = lat/lon geometry; `summary.lengthInMeters`, `travelTimeInSeconds`, `departureTime`, `arrivalTime`.
- `extendedRouteRepresentation=distance,travelTime` adds a `progress[]` array (`pointIndex`, `distanceInMeters`,
  `travelTimeInSeconds`) at the first/last point and intermediate points; docs say to linearly interpolate between them.
  This gives correct ETAs at every checkpoint.
- `departAt=<ISO datetime>` uses historical traffic for that time; `maxAlternatives` cannot be combined with `computeBestOrder`.
- Error codes to handle: `NO_ROUTE_FOUND`, `COMPUTE_TIME_LIMIT_EXCEEDED`, `BAD_INPUT`; over-quota returns HTTP 403.

Risk accepted on all providers: alternatives are best-effort. Mitigation (Phase 3): request `maxAlternatives=2`
(3 routes, ~4 s on a 1,000-mile trip); if fewer than 3 distinct routes come back, retry once with `maxAlternatives=4`
and keep the 3 most distinct by geometry overlap; if still < 3, show what exists with an explicit notice.
`routeType=shortest` / `eco` were tested as extra candidates and returned the same road as `fastest`, so they are
not used. The app must never fabricate a route.

### 1.2 Geocoding
- **TomTom Geocoding API** (same key as routing, 20K/month): geocode on submit, `countrySet=US`. Primary.
- Nominatim (OSM): works, 1 req/s, autocomplete forbidden by policy. Fallback only.
- Photon (komoot): works, no key, autocomplete allowed. Fallback only.

### 1.3 Weather — Open-Meteo (verified live)
- No key. Free non-commercial: 600/min, 5,000/hour, 10,000/day. **Confirmed live 2026-10-10: each location in a
  multi-location request counts as one call** (HTTP 429 "Minutely API request limit exceeded" after ~690 locations
  within a minute). A fresh 1,000-mile plan at 25-mile checkpoints needs ~140 locations; at 10 miles ~350.
- Live test: **300 locations in one request**, 72 hourly steps each, 3.5 s, 793 KB. Horizon up to 16 days (384 h).
- Units confirmed in the response: `wind_speed_10m` **mph**, `wind_gusts_10m` mph, `rain` **inch** (sum of preceding hour
  = in/hr), `snowfall` **inch** (preceding hour = in/hr) when `precipitation_unit=inch`. Matches PDF units exactly.
- Model resolution for the US is roughly 3–13 km, so 10-mile sampling is meaningful.

### 1.4 Map rendering
- **MapLibre GL JS 6.x** (WebGL) via `react-map-gl/maplibre` + **OpenFreeMap** vector tiles (verified HTTP 200;
  free, no key, no request limits, commercial OK, attribution auto-added). Native `heatmap` layer renders on the GPU;
  the 0–48 h slider only swaps a style expression, so no refetch and no data re-upload per tick.
- Fallback: Leaflet + CARTO raster + leaflet.heat (verified tiles respond). Not preferred: canvas heatmap redraw on
  every slider tick is less smooth.

### 1.5 Toolchain on this machine
Python 3.12.6, Node 22.12, npm 10.9, git 2.47. **Docker not installed locally** (only needed on the server).
Current versions: Django 6.1.2, DRF 3.18.3, React 19.3, Vite 8.3, MapLibre 6.13, react-map-gl 8.1, TypeScript 7.0
(may pin TS 5.9 if tooling complains).

---

## 2. Decisions and assumptions (confirm or override)

| # | Decision | Why |
|---|---|---|
| A1 | Routing = TomTom, truck mode, `departAt` = departure time. Load weight is **not** passed to routing; it is used only for the PDF risk/load rules. | PDF defines load weight's role as a risk input. Passing it to routing is an extra feature with ambiguous semantics (gross vs. cargo). |
| A2 | Sampling interval (10 / 25 / 50 mi) is a user choice in the form; checkpoints at 0, N, 2N … plus the destination. | Literal reading of "every 10 / 25 / 50 miles". |
| A3 | Checkpoint ETA = departure + interpolated travel time from TomTom `progress` data. | Correct ETA per checkpoint is the core of the 40% logic score. |
| A4 | Weather at a checkpoint = the forecast hour nearest to its ETA. | Simple, explainable, matches hourly data. |
| A5 | Wind threshold uses sustained `wind_speed_10m` (mph). Gusts are shown in the popup for information only. | PDF says "Wind". |
| A6 | Checkpoint risk = worst of wind/rain/snow level, then load rules applied (≥55 → No Travel; 45–54 & >30,000 lb → No Travel; 35–44 & >40,000 lb → Severe). | PDF rules verbatim. |
| A7 | Each stretch between two consecutive checkpoints is rated at the worse of its two endpoints; "Severe miles" / "High miles" = sum of stretch lengths at that level. | Conservative and easy to explain. |
| A8 | Recommendation = sort by (No Travel miles, Severe miles, High miles, average risk, travel time). Any route containing a No Travel checkpoint is badged "Travel not advised". If all routes have No Travel miles, the app says so and recommends none. | PDF list is kept intact; No Travel is the top of the PDF scale so it ranks above Severe. |
| A9 | Average risk = distance-weighted mean of level index (Low 0 … No Travel 4). | Deterministic, explainable. |
| A10 | Heatmap value = risk level at each checkpoint for the slider hour, 49 hourly values per checkpoint across all routes. The heatmap grid *is* the checkpoint set (10/25/50 mi), so weather is fetched exactly once per unique checkpoint. Weather is cached per ~3 km cell (0.05°) for 30 min so repeats and overlapping trips are free. (Revised 2026-10-10: a separate 10-mile grid tripled Open-Meteo usage and hit its 600 locations/min limit in the live test.) | "Weather heatmap along the trip corridor"; one set of points, one purpose; stays inside free quotas. |
| A11 | Slider hour 0 = departure time, up to +48 h; absolute time is displayed next to the slider. | Forecast relative to the trip is what the driver needs. |
| A12 | All third-party calls go through Django; keys stay server-side; responses cached (geocode 24 h, routes 1 h, weather 30 min) to protect free quotas. | Quotas + no key leakage. |
| A13 | US-focused geocoding (`countrySet=US`). | PDF units are mph/inch/lb. |
| A14 | Deployment: Docker Compose on the user's server, nginx + gunicorn, served over HTTP on the IP. HTTPS only if a domain is provided. | User has a server; no domain known yet. |

---

## 3. Architecture

```
frontend/  React 19 + TypeScript + Vite + MapLibre GL (react-map-gl/maplibre), OpenFreeMap tiles
backend/   Django + DRF; apps: routing (domain logic, pure python), providers (tomtom, openmeteo), api
deploy/    Dockerfiles, docker-compose.yml, nginx.conf, .env.example, deploy.sh
docs/      PDF, PLAN.md, QA.md
```

Single API call drives the UI:

```
POST /api/plan
{ "origin": "Chicago, IL", "destination": "Denver, CO",
  "departure_time": "2026-10-10T08:00:00-05:00", "load_weight_lb": 42000, "sample_interval_miles": 25 }

-> 200
{ "inputs": { ...resolved origin/destination names + coords... },
  "routes": [ { "id", "name", "distance_miles", "duration_seconds", "eta",
                "geometry": [[lon,lat], ...],
                "checkpoints": [ { "index", "mile", "lon", "lat", "eta",
                                   "wind_mph", "gust_mph", "rain_in_hr", "snow_in_hr",
                                   "wind_level", "rain_level", "snow_level",
                                   "level": "severe", "reason": "Wind 38 mph + load > 40,000 lb" } ],
                "summary": { "miles_by_level": {...}, "avg_risk": 1.4, "no_travel": false,
                             "worst_checkpoint_index": 7 } } ],
  "recommended_route_id": "...", "recommendation_reason": "...",
  "heatmap": { "hours": ["2026-10-10T08:00Z", ... 49 items],
               "points": [ { "lon", "lat", "levels": [0,0,1, ... 49 ints] } ] },
  "warnings": [ "Only 2 distinct routes were returned by the routing provider." ] }

GET /api/health
```

Backend pipeline: geocode -> route (3 alternatives) -> sample checkpoints -> interpolate ETAs ->
one Open-Meteo batch (checkpoints + corridor points) -> classify -> aggregate -> recommend -> respond.

---

## 4. Phased plan

Each phase has a gate that must pass before the next starts.

### Phase 0 — Accounts and provider validation — DONE 2026-10-10, gate passed
Key lives in `F:\work\tests\spotteer-fullstack\.env` as `TOMTOM_API_KEY` (gitignored in Phase 1).

Live results (truck mode, `departAt` = next day 08:00, `maxAlternatives=4`):

| Pair | Routes returned | Latency | Payload | Notes |
|---|---|---|---|---|
| Chicago → Denver | 4 | 10.2 s | 2.2 MB | r0/r3 share ~58% of road; others < 5% |
| Dallas → Atlanta | 5 | 8.4 s | 2.6 MB | at most 50% overlap between any two |
| Los Angeles → Seattle | 3 | 8.3 s | 2.5 MB | only 2 alternatives exist |
| New York → Philadelphia | 5 | 3.5 s | 0.6 MB | r0/r4 share 75% |

- `maxAlternatives=2` on Chicago → Denver: 3 routes in 4.1 s (vs 9.5 s for 4). Default to 2.
- Geocoding: all 8 test cities resolved correctly in ~0.8 s each (`/search/2/geocode/{q}.json`, `countrySet=US`).
- Progress data syntax: the parameter must be **repeated**, not comma-joined:
  `extendedRouteRepresentation=distance&extendedRouteRepresentation=travelTime`. Returns ~95–165 progress entries
  per 1,000-mile route; the last entry equals the summary distance and time exactly. Works together with alternatives.
- Routes carry 10K–21K points each on long trips. Checkpoint sampling uses the full geometry; the geometry sent to
  the browser will be simplified (Douglas–Peucker, ~50 m tolerance) to keep the payload small.
- Dev machine quirk: a corporate proxy re-signs api.tomtom.com; Python must use the Windows trust store via the
  `truststore` package in dev. Not an issue on the deploy server.

### Phase 1 — Repository scaffold — DONE 2026-10-10, gate passed
- `git init`, monorepo layout above, Django 5.2 LTS + DRF + CORS + settings split (dev/prod), Vite 8 React 19 TS app,
  `.env.example`, `.gitattributes` (LF), `README.md` skeleton, `/api/health` with a test.
- Gate: both dev servers run; `/api/health` answered through the Vite proxy and directly; `pytest`, `npm run lint`
  and `npm run build` all pass.
- Dev note: port 5173 is occupied by another process on this machine, so run Vite with `--port 5174` here.

### Phase 2 — Core domain logic, test-first (the 40% block) — DONE 2026-10-10, gate passed
Delivered in `backend/routing/` (`risk.py`, `sampling.py`, `aggregate.py`, `recommend.py`) with 108 unit
tests written before the code (red → green per module). Live smoke test on Chicago → Denver (3 real TomTom
routes + one Open-Meteo batch of 143 checkpoints): haversine mileage within 0.2% of TomTom's, interpolated
final ETA equals TomTom's total travel time, 10K-point routes simplify to ~600 points at 0.0005°.
Phase 3 note: send `departAt` with an explicit UTC offset; the smoke script relied on TomTom's
origin-timezone default.

Pure Python, no network:
- `risk.py`: threshold tables (wind/rain/snow), level enum, `classify_checkpoint(wind, rain, snow, load_lb)` with
  load rules, human-readable reason string.
- `sampling.py`: haversine, cumulative distance along polyline, checkpoint positions at every N miles + destination,
  ETA interpolation from `(distance, travel_time)` progress pairs.
- `aggregate.py`: stretch rating (A7), miles by level, average risk, no-travel flag.
- `recommend.py`: ordering (A8) and reason text.
- Unit tests on every threshold boundary (24.9/25/34/35/44/45/54/55 mph; 0.10/0.25/0.50/1.00 in; 0.5/1.0/2.0/3.0 in),
  load-rule edge cases (30,000 vs 30,001 lb; 40,000 vs 40,001 lb), sampling on synthetic polylines, tie-breaking order.
- Gate: `pytest` green; logic documented in the README section "How risk is computed".

### Phase 3 — Provider integrations and `/api/plan` — DONE 2026-10-10, gate passed
Delivered test-first in three cycles (providers with an in-memory HTTP transport, planner with stub providers and
the real Django cache, API view with a fake planner): 80 new tests, 189 total, ruff clean.
Live gate (dev server, real providers): Chicago → Denver cold 8.4 s / 109 KB, cached repeat 1.3 s, 50-mile variant
0.8 s with zero weather fetches, 10-mile variant 2.8 s fetching only new cells; NYC → Philadelphia 3.1 s;
validation, same-place, and geocode-miss errors all mapped. Real weather ranked route 1 (100 Moderate miles)
behind routes 2 and 3 on average risk, with route 2 winning on time.
Phase 6 note: the cached path is CPU-bound (~1.3 s: Douglas–Peucker over ~40K points plus ~7K risk assessments);
cache the prepared geometry per route if the UI needs it faster.

- `providers/tomtom.py` (geocode, route), `providers/openmeteo.py` (batch hourly, unit params, nearest-hour lookup).
- Caching layer (Django cache; file-based in prod so gunicorn workers share it).
- Alternatives shortfall handling; error mapping to clear API errors (geocode miss, no route, upstream quota/timeout).
- Serializer validation: departure time between now − 1 h and now + 14 days (forecast horizon); weight > 0;
  interval in {10, 25, 50}.
- Gate: real plan for Chicago→Denver returns 3 routes with ETAs, levels, summary, heatmap in a few seconds; a repeat
  call is served from cache.

### Phase 4 — Frontend: form, map, routes, checkpoints — DONE 2026-10-10, gate passed
Delivered test-first: 42 Vitest tests (formatting, risk metadata, GeoJSON shaping, API client, form, route cards,
app shell with the map mocked) plus a Playwright gate that drives the real page in headless Chromium against the
live backend: plan renders in ~1.6–2.9 s on a warm cache, cards in rank order, card click changes the selected
route, hovering a projected checkpoint shows the popup, and the production bundle (`vite build` + `vite preview`)
behaves the same. Stack: react-map-gl 8 on MapLibre GL 6 with OpenFreeMap tiles (grey "positron" at first;
switched to the coloured "liberty" style on 2026-10-11 after comparing positron, bright, liberty and fiord
screenshots of the demo trip; `lib/mapStyle.ts` holds the style and route colours with a contrast test).
The side panel, the forecast controls and the legend fold away (2026-10-11, user request for more map room):
`components/PanelToggle.tsx`, `components/Legend.tsx`; tests in App, HeatmapControls and Legend; browser gate
checked the map canvas widens from 980 to 1356 px at 1400 px wide, state survives folding, phone layout.
Two MapLibre 6 + Vite 8 pitfalls fixed and documented in `vite.config.ts`: exclude `maplibre-gl` from dependency
pre-bundling (dev) and import the worker explicitly with `?worker&url` + `setWorkerUrl` (build), otherwise the
map canvas is blank.

- Form (origin, destination, `datetime-local`, load weight lb, interval radio), loading/error states.
- Map: 3 route lines (recommended emphasized, others muted), checkpoint circles colored by level (GPU layer, not
  DOM markers), hover/click popup (ETA, wind, gust, rain, snow, level, reason), legend, fit-to-bounds.
- Route cards: distance, duration, ETA, miles-by-level bar, avg risk, "Recommended" badge, "Travel not advised"
  badge, reason text; clicking a card focuses that route.
- Gate: manual check on 3 real trips; interactions stay smooth with ~100 checkpoints per route.

### Phase 5 — Heatmap and 0–48 h slider — DONE 2026-10-10, gate passed
Delivered test-first: 30 new Vitest tests (heatmap GeoJSON shaping, hour property/clamping, MapLibre weight,
colour-ramp and zoom-scaled radius expressions, the frame-throttle hook, the slider/toggle controls, and the app
wiring) for 72 in total, plus a Playwright gate against the live backend.

Design change from the plan above: **one MapLibre heatmap layer per risk level** instead of a single layer with
`heatmap-weight = level`. A single density ramp adds overlapping kernels, so two nearby Moderate checkpoints would
render as High; with one layer per level a point only feeds the layer of its own level, density saturates at that
level's colour (`heatmap-intensity` = sqrt(2π) makes an isolated point's centre density exactly 1), and layers stack
worst-on-top. Blob radius is a zoom-exponential expression sized to one sampling interval on the ground at the
trip's latitude, so the band width follows the 10/25/50 mi choice. The slider only swaps the `h<hour>` property
the five weight expressions read; React commits the hour at most once per animation frame and the label follows
every input event.

Gate results (Chicago → Denver, 25 mi, 143 checkpoints, 49 hours):
- API: 143/143 checkpoints have the same level as the heatmap point at their ETA hour (0 beyond 48 h).
- Rendered: with the dots hidden, canvas pixels around 7 sampled points (Low, Moderate and Severe at their hours)
  classify as the expected level colour, 7/7.
- Smoothness: headless SwiftShader renders every one of the 49 hours during a 0→48 drag at ~90 ms/frame
  (software GL; the heatmap layers cost ~50 ms of that). On the real GPU (headed Chromium, Intel UHD 630) a
  five-layer restyle reaches the next painted frame in 16 ms average, 23 ms max; `idle` in 36 ms average.
  Keyboard stepping (arrows, Home) works. Production preview behaves the same.
- Controls: absolute time label ("Forecast risk at Sat, Oct 11, 01:00 (+5 h after departure)"), slider disabled when
  the heatmap is hidden, checkpoints toggle, legend explains dots vs shading; compact legend on narrow screens.

### Phase 6 — Hardening and QA — DONE 2026-10-10, gate passed
Scope kept to the edge cases listed below; no new features. Test-first additions (9 backend, 5 frontend tests):
- **Forecast horizon.** One warning names the forecast's end time and counts the checkpoint ETAs and heatmap
  hours outside it (both reuse the nearest forecast hour). Live: a departure 14 days out gets "Forecast data ends
  2026-10-25 23:00 UTC; 15 of 49 heatmap hours are outside the forecast window…".
- **Very long routes.** Deterministic cap of 500 unique weather locations per plan (`MAX_WEATHER_LOCATIONS`),
  refused with 422 `too_many_checkpoints` before any quota is spent; the message says to pick a larger interval.
  Open-Meteo counts each batched location as one call against 600/minute (confirmed live: three plans totalling
  611 locations in a minute produced a 429 on the last chunk). Miami → Seattle: 1,009 locations at 10 mi
  (refused), 406 at 25 mi and 205 at 50 mi (complete).
- **Quota exceeded mid-plan.** Weather is fetched and cached per 200-location chunk, so the chunks fetched before
  a 429 are kept and a retry a minute later only asks for the rest.
- **Clarity.** Geocode misses say "(searching US only)"; the cards header shows what the origin and destination
  resolved to ("From Toronto, KS to Denver, CO" for the input "Toronto, ON"); 400 validation errors show the
  field label and message instead of "Invalid request."
- **Confirmed already handled:** same-city trips (422), fewer than 3 routes (padding + warning; a single route is
  ranked and recommended as "Only route available."), past or too-distant departure (400 with field message),
  provider down (503 in 2.8 s with the reason), narrow layout (compact legend).

Gate: `docs/QA.md` fully ticked, 197 backend and 77 frontend tests, ruff/tsc/oxlint/build clean.

### Phase 7 — Deployment to your server — DONE 2026-10-11, gate passed
- `deploy/backend.Dockerfile` (python:3.12-slim, gunicorn 2 workers × 4 threads, 120 s timeout, non-root,
  healthcheck on `/api/health`), `deploy/frontend.Dockerfile` (node build stage → nginx:alpine),
  `deploy/nginx.conf` (static + `/api/` proxy with 120 s read timeout, gzip, immutable `/assets/`, SPA fallback),
  `docker-compose.yml` (named volume for the shared provider cache, `web` waits for a healthy `backend`,
  `WEB_PORT` override), `deploy/deploy.sh` (checks `.env`, pull, build, up, migrate, smoke test) and
  `deploy/smoke.sh` (page, health, one real plan). No `collectstatic`: the API serves no static files.
- Production settings tested (`config/tests/test_prod_settings.py`): refuse the dev secret or an empty host list,
  shared file cache from `DJANGO_CACHE_DIR`, loopback hosts always allowed for the container healthcheck.
  `deploy/deploy.sh` refuses a missing or short (< 50 chars) `DJANGO_SECRET_KEY`. Clickjacking middleware and
  nosniff/frame/referrer headers added (Django and nginx). `manage.py check --deploy` then reports only W003
  (no CSRF middleware: the API is stateless JSON with no cookies) and W004/W008 (HSTS and SSL redirect: plain
  HTTP on an IP by design, A14).
- Local Docker is not available on the dev machine (WSL disk missing), so the images were not built here.
- 2026-10-11: the server also hosts the user's primary production project, which must never be affected. The
  stack is now scoped and capped (`config/tests/test_deploy_files.py`, written red first): fixed compose project
  name `spotter-assessment`; the deploy script runs only scoped `docker compose` commands (no `--remove-orphans`,
  no `--pull`, no down/prune) and refuses to start when `WEB_PORT` is served by another service (checked for real
  with a stubbed `docker` and `ss`); memory and CPU limits on both services. The app will run on a non-80 port
  there, set through `WEB_PORT`.
- 2026-10-11, first server deploy: the stack built in 42 s and the loopback smoke test passed, but from outside
  `/api/health` answered Django's 400 because `DJANGO_ALLOWED_HOSTS` did not hold the public IP. Fixed test-first
  in `test_deploy_files.py`: `deploy.sh` refuses a loopback-only host list and hands every public entry to
  `smoke.sh`, which sends each as the `Host` header (checked against a stub HTTP app that answers 400 like Django).
  The same work fixed a silent exit in `smoke.sh`: under `pipefail` a zero-match `grep` aborted the script without
  printing the response; it now reports the body, and every curl failure is named.
- Gate passed 2026-10-11 from an outside network: `deploy/smoke.sh http://2.25.193.125:8080` and the same by
  hostname (page, health, 3-route plan in 1 s warm); headless Chromium against the public address planned the
  Loom demo trip (3 cards, "Recommended: Route 1", map with routes, checkpoints and heatmap, slider to +24 h, no
  console errors; screenshot checked). Headers from outside: nosniff, frame DENY, referrer policy, `no-cache` on
  the page, one-year immutable cache on assets. The API carried X-Frame-Options twice (Django middleware plus
  nginx); nginx now hides the upstream copy (`test_deploy_files.py`). Redeployed 2026-10-11 and checked from
  outside: the header appears once on GET and HEAD. HTTPS was considered and parked: ports 80/443 and the
  server's DNS name belong to the host's primary project and provider, so a trusted certificate needs a
  domain the user controls (A14 stands).

### Phase 8 — Documentation and walkthrough — DONE 2026-10-10, gate passed, pushed
- README: overview, architecture diagram, how risk and recommendation are computed, assumptions A1–A14, API contract,
  local setup, deployment, limitations.
- `docs/LOOM-SCRIPT.md`: 5–10 min outline (inputs → routes → checkpoints → recommendation → heatmap slider → code tour).
- Push to GitHub.
- Gate: fresh clone + README steps work end to end.

Done 2026-10-10 (TDD):
- `backend/api/tests/test_documentation.py` (15 tests) pins the docs to the code: every API error code and its
  HTTP status, the README request example against the serializer (fields, limits, intervals), the threshold table
  and load rules against `routing/risk.py`, assumptions A1–A14 against this plan, every environment variable the
  settings read against `.env.example` (caught the missing `DJANGO_CACHE_DIR`), the deploy script's required keys
  against the Deployment section, and the Loom script's section order and 5–10 min total. Written red first; the
  README gained Architecture, Limitations and Assumptions sections and `docs/LOOM-SCRIPT.md` (8:45) to turn them green.
- Gate: fresh `git clone` into a scratch directory, then the README's steps verbatim: venv + `requirements-dev.txt`,
  `migrate`, `pytest` (216 passed), `npm install`, `npm test` (77 passed), `npm run build`, `npm run lint`, then
  `runserver` + `npm run dev -- --port 5174` (5173 was taken by another project, as the README anticipates):
  `/api/health` through the Vite proxy, a cold Chicago→Denver plan in 10.4 s (3 routes, no warnings), and headless
  Chromium planning the Loom demo trip (3 cards, "Recommended: Route 1", 408 checkpoint and 394 heatmap features
  rendered, slider to +24 h, no console errors).
- Push: `main` pushed 2026-10-10 to https://github.com/Quraize/spotter-fullstack-ai (public), README Deployment
  section points at it.

### Optional (only after Phase 8, if time remains)
- Persist plans (`TripPlan` model, `GET /api/plans/<id>`) for shareable links.
- Address autocomplete (TomTom Places Suggest).
- Heatmap metric toggle (risk / wind / rain / snow).

---

## 5. Open questions
1. TomTom key (Phase 0). Or is there an existing Google Maps Platform or Mapbox account to use instead?
2. Server: OS, SSH access, can Docker be installed, is port 80 open, any domain name (for HTTPS)?
3. GitHub: org/user and repo name; public or private?
4. Any objection to assumptions A1–A14, especially A8 (No Travel ranking) and A11 (slider relative to departure)?
