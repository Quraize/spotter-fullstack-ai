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
- No key. Free non-commercial: 600/min, 5,000/hour, 10,000/day. "One HTTP request typically = one call";
  multi-location weighting is not documented, so budget as if each location counts.
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
| A10 | Heatmap value = risk level at each corridor point for the slider hour; corridor points sampled every 10 mi along all returned routes (one weather batch shared with checkpoints). | "Weather heatmap along the trip corridor" + smooth rendering. |
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
docs/      PDF, PLAN.md, LOOM-SCRIPT.md
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

### Phase 2 — Core domain logic, test-first (the 40% block)
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

### Phase 3 — Provider integrations and `/api/plan`
- `providers/tomtom.py` (geocode, route), `providers/openmeteo.py` (batch hourly, unit params, nearest-hour lookup).
- Caching layer (Django cache; file-based in prod so gunicorn workers share it).
- Alternatives shortfall handling; error mapping to clear API errors (geocode miss, no route, upstream quota/timeout).
- Serializer validation: departure time between now − 1 h and now + 14 days (forecast horizon); weight > 0;
  interval in {10, 25, 50}.
- Gate: real plan for Chicago→Denver returns 3 routes with ETAs, levels, summary, heatmap in a few seconds; a repeat
  call is served from cache.

### Phase 4 — Frontend: form, map, routes, checkpoints
- Form (origin, destination, `datetime-local`, load weight lb, interval radio), loading/error states.
- Map: 3 route lines (recommended emphasized, others muted), checkpoint circles colored by level (GPU layer, not
  DOM markers), hover/click popup (ETA, wind, gust, rain, snow, level, reason), legend, fit-to-bounds.
- Route cards: distance, duration, ETA, miles-by-level bar, avg risk, "Recommended" badge, "Travel not advised"
  badge, reason text; clicking a card focuses that route.
- Gate: manual check on 3 real trips; interactions stay smooth with ~100 checkpoints per route.

### Phase 5 — Heatmap and 0–48 h slider
- MapLibre heatmap layer over corridor points; `heatmap-weight` = `['get', 'h<hour>']`; the slider changes only the
  expression (no refetch), throttled with requestAnimationFrame; shows absolute time; checkpoint layer can be toggled.
- Gate: dragging the slider is visibly smooth; levels on the map agree with the checkpoint popups at matching hours.

### Phase 6 — Hardening and QA
- Edge cases: same-city trips, < 3 routes, departure in the past, ETAs beyond the 16-day horizon, provider down,
  quota exceeded, very long routes (checkpoint count), narrow/mobile layout.
- Frontend type-check + production build; a few vitest tests for formatting/sorting helpers.
- Gate: QA checklist in `docs/QA.md` fully ticked.

### Phase 7 — Deployment to your server
- Dockerfiles (backend: gunicorn; frontend: static build), `docker-compose.yml` (nginx serves static + proxies
  `/api`), `.env` on the server, `deploy.sh` (pull, build, up, migrate, collectstatic).
- Gate: `http://<server-ip>/` serves the app and a real plan completes from an outside network.

### Phase 8 — Documentation and walkthrough
- README: overview, architecture diagram, how risk and recommendation are computed, assumptions A1–A14, API contract,
  local setup, deployment, limitations.
- `docs/LOOM-SCRIPT.md`: 5–10 min outline (inputs → routes → checkpoints → recommendation → heatmap slider → code tour).
- Push to GitHub.
- Gate: fresh clone + README steps work end to end.

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
