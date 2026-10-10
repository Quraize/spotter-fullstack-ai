# Loom walkthrough script

Target length 8–9 minutes (the assessment asks for 5–10). Section headings carry their time budget; the backend
test suite checks that the budgets add up to between 5 and 10 minutes and that the sections follow the demo order.

**Before recording**

- Open the deployed app (or `npm run dev` + `runserver` locally) at 1440×900, browser zoom 100%.
- Plan the demo trip once so routes and weather are cached and the on-camera plan returns in about 2 s.
- Demo trip: **Chicago, IL → Denver, CO**, departure tomorrow 08:00, load **42,000 lb**, interval **25 mi**.
  Backup trip for visible weather: on the day, pick any route with a Moderate or worse checkpoint (the heatmap at
  +12 h or +24 h usually shows one somewhere between the Plains and the Rockies).
- Editor tabs, in this order: `backend/routing/risk.py`, `backend/routing/tests/test_risk.py`,
  `backend/routing/recommend.py`, `backend/api/planner.py`, `frontend/src/lib/heatmap.ts`.
- A terminal in `backend/` ready to run `pytest`, and one in `frontend/` for `npm test`.

## 0. Intro (0:30)

Say: "This is a weather-aware truck routing app. A driver enters where they start, where they are going, when they
leave and how heavy the load is. The app gets three truck routes, samples the forecast along each one at the time
the truck will actually be there, rates every checkpoint with the assessment's thresholds and load rules, and
recommends the safest route. React and MapLibre in the browser, Django on the server, TomTom for routes, Open-Meteo
for weather."

Show: the empty app, form on the left, map on the right.

## 1. Inputs (0:45)

Say: "Four inputs from the brief: origin, destination, departure date and time, load weight. One extra choice the
brief leaves open: how often to sample the weather, every 10, 25 or 50 miles."

Show: type the demo trip. Point out the departure defaults to the next hour and the load is in pounds. Mention
validation lives on the server: a departure in the past or more than 14 days out comes back as a field error
(do not demo, just say it).

Click **Plan routes**.

## 2. Three routes (1:00)

Say: "Three distinct truck routes from TomTom, drawn on the map and summarised in the cards: distance, travel
time, arrival, and miles at each risk level. The selected route is blue; click a line or a card to switch."

Show: click Route 2's card, then Route 3's line on the map; the selection follows. Note the arrival time
changes per route and that the geometry comes straight from the routing provider: the app never invents a road.

## 3. Checkpoints and ETAs (1:15)

Say: "Every 25 miles there is a checkpoint, plus one at the destination. Each checkpoint has its own ETA,
interpolated from TomTom's timing points, and the weather shown is the forecast for that hour, not for now."

Show: hover three checkpoints along the selected route, early, middle and late. Read one popup aloud: ETA,
sustained wind, gusts, rain, snow, the level and the rule that set it. Point out the ETA advancing with the
mile marker.

## 4. Risk levels and route summaries (0:45)

Say: "Risk is the brief's table: wind in mph, rain and snow in inches per hour, five levels from Low to No Travel.
The load rules escalate wind: 45 to 54 mph with more than 30,000 lb is No Travel, 35 to 44 with more than 40,000 lb
is Severe. A checkpoint takes the worst of wind, rain and snow."

Show: the legend on the map, and the miles-by-level strip on each card. If the backup trip has a Severe checkpoint,
hover it and read the rule text, which names the load rule.

## 5. Recommendation (1:00)

Say: "The recommendation follows the brief's order exactly: fewest Severe miles, then fewest High miles, then the
lowest average risk, then the shortest travel time. The banner says which criterion decided it. One addition on
top of the brief: No Travel is the top of its own scale, so a route with a No Travel checkpoint is compared on
that first and is never recommended; if all three have one, the app says so and recommends none."

Show: the recommendation banner and its reason; the ranked order of the cards. Mention that ties are compared
at a tenth of a mile so floating-point noise never flips a result.

## 6. Heatmap and the 0–48 h slider (1:15)

Say: "The corridor shading is the forecast risk for this load at any hour from departure to 48 hours later.
Hour 0 is departure; the absolute time is shown. The data is already in the browser, so dragging the slider
makes no network call: each risk level is its own GPU heatmap layer, and the slider only changes which hour
the layers read."

Show: drag the slider slowly from departure to +48 h and back, then use the arrow keys. Toggle **Checkpoints**
off to show the shading alone, then **Heatmap** off to show the dots alone. Point out that the shading at a
checkpoint matches that checkpoint's popup when the slider sits on its ETA hour.

## 7. Code tour (1:45)

Show, in this order, 20 seconds each:

- `backend/routing/risk.py`: the three threshold tables and the load rules as data; `assess()` combines them.
  Pure Python, no Django, no network.
- `backend/routing/tests/test_risk.py`: every band boundary has a test, including the boundary convention
  (0.25 in/hr of rain is High; exactly 1.00 in/hr is Severe, only above it is No Travel).
- `backend/routing/recommend.py`: the sort key in the brief's order, with No Travel miles in front.
- `backend/api/planner.py`: the pipeline in `plan()`: geocode, routes, checkpoints with ETAs, weather once per
  unique checkpoint, assess, summarise, recommend, heatmap. Caching and quota handling live here.
- `frontend/src/lib/heatmap.ts`: the per-level weight and colour expressions the slider swaps.
- Terminal: run `pytest` in `backend/` and `npm test` in `frontend/`; read the totals off the screen.

Say: "Everything was built test-first; the domain logic has no I/O so the thresholds are tested exactly."

## 8. Deployment, limits and close (0:30)

Say: "It runs as two containers behind nginx on a single server; one script pulls, rebuilds, migrates and
smoke-tests. Known limits are listed in the README: US-only geocoding, a 14-day departure window against a
16-day forecast, and a cap of 500 weather locations per plan so a cross-country trip at 10 miles asks you to
pick a wider interval. Thanks for watching."

Show: the README's Limitations section, then back to the map with the recommended route selected.
