# QA checklist

How the app was verified against `fs-assessment-spotter.pdf`. Every box was ticked on 2026-10-10 against the live
TomTom and Open-Meteo APIs. Automated tests run with `pytest` (backend) and `npm test` (frontend); the browser
checks drove the real page in headless Chromium with Playwright and, for GPU timings, a headed Chromium.

## 1. PDF requirements

| # | Requirement (PDF) | Where | Automated | Live check |
|---|---|---|---|---|
| 1 | Inputs: origin, destination, departure date/time, load weight | `PlanForm.tsx`, `serializers.py` | PlanForm, plan_api tests | [x] form submits; server validates |
| 2 | Generate 3 route options via a routing API | `planner._select_routes`, `tomtom.routes` | planner retry/fill tests, tomtom tests | [x] Chicago→Denver, Miami→Seattle: 3 distinct routes |
| 3 | Sample weather every 10 / 25 / 50 miles at the truck's ETA | `sampling.py`, `planner._prepare` | sampling tests (spacing, destination), ETA interpolation test | [x] 25 mi: 41–54 checkpoints per 1,000 mi route; ETAs increase with mile |
| 4 | Risk thresholds and load rules | `routing/risk.py` | every boundary in `test_risk.py` | [x] real Severe/No Travel checkpoints seen (gusty Florida weather, 42,000 lb) |
| 5 | Recommend the best route (Severe → High → average → time) | `routing/recommend.py` | `test_recommend.py`, planner ranking tests | [x] reasons shown: "Fewest No Travel miles…", "Shortest travel time…" |
| 6 | Show routes, checkpoints, risk levels, ETAs, summaries on a map | `MapView.tsx`, `RouteCards.tsx` | RouteCards/App tests, geojson tests | [x] popups show ETA + weather + rule; cards show distance, time, arrival, miles by level |
| 7 | Weather heatmap along the corridor with a 0–48 h slider | `lib/heatmap.ts`, `HeatmapControls.tsx` | heatmap expression tests, controls tests, throttle hook | [x] 143/143 checkpoints match heatmap at ETA hour; 7/7 pixel samples right colour; all 49 hours render during a drag |

## 2. Edge cases (plan Phase 6)

| Case | Expected | Observed | |
|---|---|---|---|
| Same city ("Chicago, IL" → "Chicago") | 422 `invalid_trip`, clear message | "Origin and destination resolve to the same place." shown in the UI | [x] |
| Unknown place ("Xqzvwk Plrmt") | 422 `geocode_not_found` | "No location found for 'Xqzvwk Plrmt' (searching US only)." | [x] |
| Foreign city ("Toronto, ON") | US-only geocoding resolves a US namesake; UI must show it | Resolved to Toronto, KS; cards header reads "From Toronto, KS to Denver, CO" | [x] |
| Departure in the past (−3 h) | 400 with a field message | UI alert: "Departure date & time: Departure time is in the past." | [x] |
| Departure > 14 days ahead | 400 with a field message | "Departure must be within the next 14 days (forecast horizon)." | [x] |
| Interval 15, load 0, load 200,000 | 400, 400, 200 | as expected | [x] |
| Departure 14 days ahead (16-day forecast cap) | plan completes, warning names the forecast end | "Forecast data ends 2026-10-25 23:00 UTC; 15 of 49 heatmap hours are outside the forecast window and use the nearest available forecast hour." | [x] |
| ETAs beyond the forecast (unit) | nearest hour used, counted in the same warning | `test_warns_with_the_forecast_end_when_etas_and_heatmap_hours_fall_after_it` | [x] |
| Short trip (Chicago → Evanston, 50 mi) | 2 checkpoints per route (origin, destination) | 3 routes of 13–19 mi, 2 checkpoints each | [x] |
| One road only (Key West → Marathon) | 1 route, still ranked and recommended, warning | "Only route available." + "The routing provider returned only 1 distinct route for this trip." | [x] |
| Fewer than 3 routes (unit) | retry with 4 alternatives, then pad with a warning | planner retry/fill tests | [x] |
| Very long trip, 10 mi (Miami → Seattle) | refused before any weather call, message says to pick a larger interval | 422 `too_many_checkpoints`: "needs weather for 1009 locations … more than the 500 … Choose a larger sampling interval." | [x] |
| Very long trip, 50 mi | plan completes | 3 routes of 3,361–3,495 mi, 205 weather locations, 3.8 s with routes cached, 11.4 s cold | [x] |
| Very long trip, 25 mi | 406 locations, under the cap, completes | 3 routes, 136–141 checkpoints each, 406 weather locations, 17.7 s cold | [x] |
| Provider down (both base URLs pointed at a closed port) | 503 `provider_unavailable`, clear message, no hang | "TomTom is unreachable: … actively refused it" in 2.8 s | [x] |
| Weather quota exceeded | 503 `provider_quota_exceeded` with the provider's retry advice | Triggered for real by 611 locations in one minute: "Open-Meteo rate limit exceeded (Minutely API request limit exceeded. Please try again in one minute.)"; weather is now fetched and cached per 200-location chunk so a retry only asks for the rest (unit test) | [x] |
| Routing quota / key rejected (unit) | 403/429 → 503 `provider_quota_exceeded` | tomtom tests | [x] |
| Missing TomTom key | 503 `provider_unavailable` naming TomTom | plan_api test | [x] |
| Narrow / mobile layout (420 px) | form, cards, map and controls usable; compact legend | Phase 5 screenshot; legend collapses to one row | [x] |

## 3. UI, map and heatmap performance

| Check | Result | |
|---|---|---|
| Plan render, 1,000 mi, warm cache | 1.4–2.9 s from click to cards | [x] |
| Plan render, 3,400 mi, cold | 11.9 s (TomTom response for three 3,400-mile truck routes dominates) | [x] |
| Cached plan CPU path | ~1.3 s for 1,000 mi (geometry simplification + 150 assessments) | [x] |
| Slider restyle on a real GPU (Intel UHD 630) | next painted frame in 16 ms avg, 23 ms max | [x] |
| Slider sweep in headless software GL | ~90 ms/frame for both 143 and 211 checkpoints (cost does not grow with trip length) | [x] |
| Checkpoint and heatmap layers | GPU layers (circle + heatmap), not DOM markers; 211 checkpoints + 205 heatmap points render without lag | [x] |
| Production bundle (`vite build` + `vite preview`) | identical behaviour to dev; worker bundled | [x] |

## 4. Automated suites at the end of Phase 8

| Suite | Count |
|---|---|
| Backend `pytest` | 216 (incl. 15 documentation-contract tests) |
| Frontend `vitest` | 77 |
| `ruff check` / `ruff format --check` | clean |
| `tsc -b`, `vite build`, `oxlint` | clean |

## 5. Known limitations

- Geocoding is US-only; a foreign city may resolve to a US namesake. The resolved names are shown above the cards.
- Open-Meteo forecasts end 16 days out; later slider hours or checkpoint ETAs reuse the last forecast hour and the
  plan says so.
- One plan may use at most 500 weather locations; a 10-mile grid on a cross-country trip is refused with advice.
- Two long cold-cache plans within the same minute can exceed Open-Meteo's 600 locations/minute; the second gets a
  503 with the provider's "try again in one minute" and its already-fetched chunks are cached.
- Route timing is cached per 15-minute departure bucket; ETAs always use the exact departure entered.

## 6. Deployment gate (2026-10-11, shared server, port 8080)

| Check | Result | |
|---|---|---|
| `deploy/deploy.sh --no-pull` on the server | images built in 42 s cold, 1 s cached; both containers healthy; migrations applied; internal smoke test passed including the `Host:` checks for the public IP and hostname | [x] |
| `deploy/smoke.sh http://2.25.193.125:8080` from outside | page, health and a 3-route plan ok, by IP and by hostname | [x] |
| Headless Chromium against the public address | Loom demo trip planned: 3 cards, "Recommended: Route 1", routes, checkpoints and heatmap rendered, slider to +24 h, no console errors | [x] |
| Response headers from outside | nosniff, X-Frame-Options DENY, Referrer-Policy; `no-cache` page; one-year immutable assets; X-Frame-Options sent once on `/api` after the 2026-10-11 redeploy | [x] |
| Coexistence with the server's primary project | compose project `spotter-assessment`, its own network and volume; port 80 untouched; memory/CPU caps | [x] |
| Wrong `DJANGO_ALLOWED_HOSTS` | found by the first external check (400 from Django); the deploy script now refuses a loopback-only list and the smoke test sends each public host as `Host` | [x] |
