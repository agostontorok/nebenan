# Map Clustering and Geocoding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate the timetable map by geocoding unlocated events and replace stacking markers with zoom-driven clusters that drill down to single events while the side list filters to the selected place.

**Architecture:** Geocoding runs server-side through the existing `Collector.geocode()` pipeline (Nominatim, 1.1s politeness sleep, geocache keyed by `street, city`), looped until all distinct streets resolve, then the static export is regenerated. Client-side, a new pure module (`map-clusters.mjs`) groups located events into zoom-scaled grid cells; the `MapView` component renders one badge per multi-event cell and a single pin per lone event, and the App component holds a "selected place" coordinate key set that filters the timetable and is cleared by clicking the map background.

**Tech Stack:** Python 3 (FastAPI app, BeautifulSoup, Nominatim via existing fetch), TypeScript + React 19 + Leaflet 1.9 (divIcon markers, LayerGroup), Node `node:test` for `web/src/*.test.mjs`, pytest for `tests/*.py`.

---
## File Structure

- **Modify** `app/collect.py` — add a loop helper that runs `geocode()` to completion over all unresolved streets (Task 1).
- **Create** `app/backfill_geocode.py` — CLI entry (`python -m app.backfill_geocode`) that warms the geocache for every unresolved street, runs geocode, then regenerates `web/public/data.json` (Task 2).
- **Test:** `tests/test_backfill_geocode.py` — verifies the loop stops, uses the cache, and only geocodes street addresses (Task 1-2).
- **Create** `web/src/map-clusters.mjs` — pure cluster-group functions (Task 3).
- **Test:** `web/src/map-clusters.test.mjs` (Task 3).
- **Modify** `web/src/main.tsx` — MapView render + selected-place state + caption + clear chip (Tasks 4-8).
- **Modify** `web/src/style.css` — cluster badge + selected-place chip styles (Task 7).
- **Modify** `web/src/i18n.mjs` — new strings for caption + clear-place chip (Task 8).
- **Modify** `web/src/map-policy.mjs` — expose zoom-aware fit policy for cluster drill-down (Task 6, optional if inlined).
- **Test:** `web/src/map-policy.test.mjs` (Task 6, optional).

---

## Task 1: Geocode-loop helper in `app/collect.py`

**Files:**
- Modify: `app/collect.py:587-625`
- Test: `tests/test_backfill_geocode.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_backfill_geocode.py`:

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.backfill_geocode import unresolved_streets
from app.collect import Collector
from app.db import Database

TZ = ZoneInfo('Europe/Berlin')
NOW = datetime(2026, 9, 14, 12, tzinfo=TZ)


def _published_event(eid, address):
    return {
        'external_id': str(eid),
        'url': f'https://example.com/event/{eid}',
        'id': eid,
        'title': 'Kurs',
        'start': '2026-09-14T12:00:00+02:00',
        'venue': 'Volkshochschule',
        'address': address,
        'description': '',
        'topics': [],
        'scale': 'small',
        'free': None,
        'lat': None,
        'lon': None,
        'status': 'published',
        'area': 'Darmstadt',
    }


def test_unresolved_streets_skips_located_and_matches_street_pattern(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    db.upsert_event(_published_event(1, 'Schöfferstraße 3, 64285 Darmstadt'), 'nbh', NOW.isoformat())
    db.upsert_event(_published_event(2, 'Rathaus, Marktplatz'), 'nbh', NOW.isoformat())
    db.upsert_event(
        {**_published_event(3, 'Oberstraße 20, Darmstadt'), 'lat': 49.87, 'lon': 8.65,
         'coordinate_evidence': 'https://nominatim.openstreetmap.org/search?...'},
        'nbh', NOW.isoformat())
    streets = unresolved_streets(db)
    assert 'schöfferstraße 3' in streets
    assert 'marktplatz' not in streets
    assert 'oberstraße 20' not in streets


def test_backfill_loop_stops_when_all_resolved(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    db.upsert_event(_published_event(1, 'Schöfferstraße 3, 64285 Darmstadt'), 'nbh', NOW.isoformat())
    hits = []
    def fetch(url):
        hits.append(url)
        return b'[{"lat": "49.872", "lon": "8.651", "display_name": "Schöfferstraße 3, Darmstadt", "address": {"house_number": "3"}}]'
    monkeypatch.setattr('app.backfill_geocode.fetch', lambda url: fetch(url))
    Collector(db, fetch=fetch, now=lambda: NOW).geocode(limit=10)
    event = [e for e in db.events('published') if e['id'] == 1][0]
    assert event['lat'] == pytest.approx(49.872, abs=0.001)
    assert event['lon'] == pytest.approx(8.651, abs=0.001)
    assert event['coordinate_evidence'].startswith('https://nominatim')
```

Then run:

```bash
cd /Users/agostontorok/Documents/code/nebenan
.venv/bin/python -m pytest tests/test_backfill_geocode.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.backfill_geocode'`.

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_backfill_geocode.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.backfill_geocode'`.

- [x] **Step 3: Create `app/backfill_geocode.py`**

```python
"""Warm the geocache for every unresolved street, then geocode to completion.

Existing collection runs cap geocoding at 20 new Nominatim lookups per run so
the map only fills slowly over weeks. This backfill resolves every street that
has not been geocoded yet, respecting the same 1.1 s politeness sleep.
"""
import json
import logging
import os
import sys

from .collect import Collector, street_address, infer_area, now_local
from .db import Database, ROOT
from .export_static import collect as collect_payload
from .network import fetch

log = logging.getLogger(__name__)


def unresolved_streets(db):
    """Distinct street keys for published events lacking a resolved location."""
    seen = set()
    for event in db.events('published'):
        if event.get('lat') is not None and not str(event.get('coordinate_evidence') or '').startswith('Approximate'):
            continue
        street = street_address(event.get('address') or '')
        if not street:
            continue
        city = infer_area(event.get('address') or '') or 'Darmstadt'
        seen.add(street.casefold() + ', ' + city.casefold())
    return seen


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    db = Database(os.environ.get('DARMSTADT_DB'))
    collector = Collector(db, fetch=fetch, now=now_local)
    pending = unresolved_streets(db)
    limit = int(args[0]) if args else max(1, len(pending))
    collector.geocode(limit=limit)
    payload = collect_payload(db)
    out = ROOT / 'web/public/data.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    log.info('geocoded up to %s new streets; exported %s', limit, out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_backfill_geocode.py -v`
Expected: PASS (2 passed).

- [x] **Step 5: Run the full Python suite**

Run: `.venv/bin/python -m pytest tests -v 2>&1 | tail -5`
Expected: all pass (no regressions from new module import).

- [x] **Step 6: Commit**

```bash
git add app/backfill_geocode.py tests/test_backfill_geocode.py
git commit -m "feat: backfill geocoder warms cache and re-exports static map data"
```

---

## Task 2: Run the backfill against the live database

**Files:** No source changes; operational step (later amended with a geocode acceptance fix, see "Outcome" below).

- [x] **Step 1: Run the backfill**

Run: `cd /Users/agostontorok/Documents/code/nebenan && .venv/bin/python -m app.backfill_geocode`
Took ≈ 70 s, exited 0. First pass resolved only 12 of ~61 streets because `Collector.geocode()` requires exactly ONE Nominatim row with a house_number. → **Amended:** fixed `app/collect.py` to accept the first row with a house_number (commit `c0a00a1`), deleted the 43 permanent miss rows from `data/events.sqlite` (misses are cached forever by design, so clearing them was required for a retry), and re-ran (≈ 57 s).

- [x] **Step 2: Verify the export grew**

Run the `node -e` count snippet (above).
**Actual result:** `total 2118, with coords 555, unique coords 62` (plan estimated ~573/~75; the gap is exactly the 6 streets that remain genuinely unlocalizable — e.g. `Hof der alten Schlossschule` is a venue name, not a street — covering only 11 events total). Re-ran `VITE_STATIC=1 npx vite build` so the served `web/dist/data.json` (which the uvicorn server at :8765 actually serves) reflects the new coordinates.

- [x] **Step 3: Commit the data export — SKIPPED by user decision**

`web/public/data.json` (4.5 MB generated artifact) is gitignored (`.gitignore:8`). The user chose to keep it untracked: the file exists on disk and is served, but is not versioned. `data/events.sqlite` also stays untracked. No commit for this step.

Do NOT commit `data/events.sqlite` here unless the user explicitly asks (the SQLite is a separate open decision).

---

## Task 3: Cluster-grouping module (`web/src/map-clusters.mjs`)

> **Outcome:** DONE — `web/src/map-clusters.mjs` + `web/src/map-clusters.test.mjs` committed verbatim per spec (`21283db`); added 2 guard tests for null/zero-coordinate skipping and empty input (`e3e065b`). Web tests: 27 → 36 pass (7 spec tests + 2 guard tests). Reviewer (spec + quality): **Approved**, no changes needed.

> **Accepted deviation (none in Task 3). Note for Task 4:** reviewer flagged that the render effect must track real map zoom or badges never subdivide — addressed as Task 4's zoom-state fix below.

**Files:**
- Create: `web/src/map-clusters.mjs`
- Test: `web/src/map-clusters.test.mjs`

- [x] **Step 1: Write the failing test**

Create `web/src/map-clusters.test.mjs`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  coordKey,
  cellSize,
  cellCenter,
  groupEvents,
  locationCount,
} from "./map-clusters.mjs";

const ev = (id, lat, lon) => ({ id, lat, lon, title: `E${id}` });

test("coordKey collapses float representation and is stable", () => {
  assert.equal(coordKey(49.8728, 8.6512), "49.87280,8.65120");
  assert.equal(coordKey(49.8728, 8.6512), coordKey(49.8728, 8.6512));
});

test("cellSize halves as zoom increases and is finite", () => {
  const s13 = cellSize(13);
  assert.ok(s13 > 0);
  assert.equal(cellSize(14), s13 / 2);
  assert.equal(cellSize(16), s13 / 8);
  assert.ok(Number.isFinite(cellSize(19)));
});

test("identical coordinates share one cell at every zoom", () => {
  for (let z = 10; z <= 19; z++) {
    const groups = groupEvents(
      [ev(1, 49.8728, 8.6512), ev(2, 49.8728, 8.6512), ev(3, 49.8728, 8.6512)],
      z,
    );
    assert.equal(groups.length, 1);
    assert.equal(groups[0].events.length, 3);
  }
});

test("nearby distinct coordinates separate at deeper zooms", () => {
  const a = ev(1, 49.8728, 8.6512);
  const b = ev(2, 49.8729, 8.6513);
  const coarse = groupEvents([a, b], 13);
  assert.equal(coarse.length, 1);
  const fine = groupEvents([a, b], 17);
  assert.equal(fine.length, 2);
});

test("far apart coordinates never share a cell", () => {
  const groups = groupEvents(
    [ev(1, 49.87, 8.65), ev(2, 49.76, 8.59)],
    10,
  );
  assert.equal(groups.length, 2);
});

test("locationCount counts distinct coordinate pairs", () => {
  assert.equal(locationCount([ev(1, 49.87, 8.65), ev(2, 49.87, 8.65), ev(3, 49.76, 8.59)]), 2);
});

test("cellCenter places the point inside its own cell", () => {
  const { lat, lon } = cellCenter(49.8728, 8.6512, 13);
  assert.ok(Math.abs(lat - 49.8728) < cellSize(13));
  assert.ok(Math.abs(lon - 8.6512) < cellSize(13));
});
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npm test -- --test-name-pattern="map-clusters"`
Expected: FAIL with module-not-found.

- [x] **Step 3: Implement the module**

Create `web/src/map-clusters.mjs`:

```javascript
export function coordKey(lat, lon) {
  return `${lat.toFixed(5)},${lon.toFixed(5)}`;
}

export function cellSize(zoom) {
  return 0.0025 * Math.pow(2, 13 - zoom);
}

export function cellCenter(lat, lon, zoom) {
  const size = cellSize(zoom);
  const cellLat = Math.floor(lat / size) * size + size / 2;
  const cellLon = Math.floor(lon / size) * size + size / 2;
  return { lat: cellLat, lon: cellLon };
}

export function groupEvents(events, zoom) {
  const groups = new Map();
  for (const e of events) {
    if (e.lat == null || e.lon == null || !Number.isFinite(e.lat) || !Number.isFinite(e.lon)) continue;
    const { lat, lon } = cellCenter(e.lat, e.lon, zoom);
    const key = `${lat.toFixed(6)},${lon.toFixed(6)}`;
    let g = groups.get(key);
    if (!g) {
      g = { lat, lon, events: [] };
      groups.set(key, g);
    }
    g.events.push(e);
  }
  return [...groups.values()];
}

export function locationCount(events) {
  const keys = new Set();
  for (const e of events) {
    if (e.lat == null || e.lon == null || !Number.isFinite(e.lat) || !Number.isFinite(e.lon)) continue;
    keys.add(coordKey(e.lat, e.lon));
  }
  return keys.size;
}
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npm test -- --test-name-pattern="map-clusters"`
Expected: PASS.

- [x] **Step 5: Run entire web test suite**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npm test`
Expected: all pass (27 existing + 6 new).

- [x] **Step 6: Commit**

```bash
git add web/src/map-clusters.mjs web/src/map-clusters.test.mjs
git commit -m "feat: zoom-scaled cluster grouping for map markers"
```

---

## Task 4: Rewrite `MapView` to render clusters

> **Outcome:** DONE — committed in `30b1eda` (spec-verbatim) + `8f40d39` (**plan deviation, required**): code-quality reviewer found the approved effect shape reads `m.getZoom()` at render and never re-runs on zoom, so cluster badges froze at the initial zoom and repeated drill-down clicks stalled (the closure's `zoom` never advanced). Fixed by driving grouping from a `zoom` state updated by a `m.on("zoomend")` listener (`setZoom(m.getZoom())`), making the render effect depend on it; this is what makes cluster → zoom → re-cluster → single pins actually work. Also dropped the now-unused `index` param. Accepted deviation: `(g.events as EventItem[])` cast at the cluster-key computation, required because `map-clusters.mjs` is untyped (`checkJs:false`).

**Files:**
- Modify: `web/src/main.tsx:195-312` (`MapView` component)
- Test: verification only (typescript build + manual)

- [x] **Step 1: Read the current MapView**

Confirm the current block spans `function MapView(` through the closing brace before `function EventForm(` (~lines 195-312 of `web/src/main.tsx`).

- [x] **Step 2: Add the new imports at the top of `main.tsx`**

After the existing `import { shouldFitInitialMap } from "./map-policy.mjs";` line insert:

```typescript
import { coordKey, groupEvents, locationCount } from "./map-clusters.mjs";
```

- [x] **Step 3: Update the component signature and map events**

Change the `MapView` props destructure and type annotation. The new handlers are optional in TypeScript so the component compiles before App passes them (Task 5):

```typescript
function MapView({
  events,
  onSelect,
  onSelectPlace,
  onClearPlace,
  language,
}: {
  events: EventItem[];
  onSelect: (e: EventItem) => void;
  onSelectPlace?: (keys: string[]) => void;
  onClearPlace?: () => void;
  language: "en" | "de";
}) {
```

In the map-init effect, after `m.on("dragstart zoomstart", ...)` add a background-click handler that clears the selection. Leaflet stops propagation on interactive markers, so a plain map `click` fires only for the background (tiles/blank area), not for pins or badges:

```typescript
    m.on("click", () => onClearPlace?.());
```

- [x] **Step 4: Rewrite the marker-render effect**

Replace the effect body that called `layer.current?.clearLayers()` and looped markers with:

```typescript
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const zoom = m.getZoom();
    layer.current?.clearLayers();
    const coords: L.LatLngTuple[] = [];
    const groups = groupEvents(events, zoom);
    groups.forEach((g, index) => {
      const pos: L.LatLngTuple = [g.lat, g.lon];
      coords.push(pos);
      if (g.events.length === 1) {
        const e = g.events[0];
        L.marker(pos, {
          keyboard: true,
          title: e.title,
          icon: L.divIcon({
            className: "event-pin",
            html: `<span></span>`,
            iconSize: [32, 38],
            iconAnchor: [16, 38],
          }),
        })
          .on("click", () => onSelect(e))
          .addTo(layer.current!);
        return;
      }
      const count = g.events.length;
      L.marker(pos, {
        keyboard: true,
        title: `${count} ${language === "de" ? "Termine" : "events"}`,
        icon: L.divIcon({
          className: "cluster-pin",
          html: `<span>${count}</span>`,
          iconSize: [44, 44],
          iconAnchor: [22, 22],
        }),
      })
        .on("click", () => {
          const keys = g.events.map((e) => coordKey(e.lat!, e.lon!));
          onSelectPlace?.(keys);
          m.setView(pos, Math.min(zoom + 1, 19), { animate: true });
        })
        .addTo(layer.current!);
    });
    if (
      shouldFitInitialMap({
        hasFitted: hasFitted.current || userInteracted.current,
        coordinateCount: coords.length,
      })
    ) {
      hasFitted.current = true;
      map.current?.fitBounds(L.latLngBounds(coords), {
        padding: [45, 45],
        maxZoom: 14,
      });
    }
  }, [events, onSelect, onSelectPlace, language]);
```

- [x] **Step 5: Update the caption**

Update the caption block (lines ~304-309) to show real counts via the new `locationCount` import:

```typescript
      <div className="map-caption">
        <span className="live-dot" /> {t(language, "results.areaCaption")}{" "}
        <span>
          {locationCount(events)} {language === "de" ? "Orte /" : "places ·"}{" "}
          {events.filter((e) => e.lat != null && e.lon != null).length}{" "}
          {language === "de" ? "Termine" : "events"}
        </span>
      </div>
```

- [x] **Step 6: Typecheck and build**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npx tsc --noEmit`
Expected: PASS even before Task 5, because `onSelectPlace`/`onClearPlace` are optional (`?.` guard) and unused App props are not an error (`noUnusedLocals` is unset).
Then: `VITE_STATIC=1 npx vite build`
Expected: build succeeds.

- [x] **Step 7: Commit**

```bash
git add web/src/main.tsx
git commit -m "feat: render clustered map markers with drill-down badges"
```

---

## Task 5: Wire selected-place state in the App component

> **Outcome:** DONE — committed in `5871563` (spec-verbatim) + `fb12ab8` (reviewer fixes): empty-state **Reset** button also calls `setPlaceKeys(null)` (otherwise Reset left the list stuck empty when the active place was excluded by the pre-reset filters), and the slots-pill count now uses `placeFiltered.length` (it previously showed `filtered.length`, e.g. "52 slots" above a 4-event place-filtered list). Deferred to Task 8 by plan: visible clear-place chip; stale-filter intersection when the active place is excluded by a filter change is still cleared only via All chip / Reset / chip-× (acceptable per plan). Quality review: **Approved**.

**Files:**
- Modify: `web/src/main.tsx:640-665` (state block), `:728-761` (filtered memo), `:1168-1361` (list + map)

- [x] **Step 1: Add state**

In the state block (after `[evening, setEvening]`), add:

```typescript
    [placeKeys, setPlaceKeys] = useState<string[] | null>(null),
```

- [x] **Step 2: Add selectors and filtered variants**

After the `selectEvent` line (`~799`) add:

```typescript
  const selectPlace = React.useCallback((keys: string[]) => setPlaceKeys(keys), []);
  const clearPlace = React.useCallback(() => setPlaceKeys(null), []);
  const placeFiltered = useMemo(() => {
    if (!placeKeys) return filtered;
    const keySet = new Set(placeKeys);
    return filtered.filter((e) => e.lat != null && e.lon != null && keySet.has(coordKey(e.lat, e.lon)));
  }, [filtered, placeKeys]);
```

- [x] **Step 3: Point the timetable at `placeFiltered`**

In the timetable memo (line ~843), replace the dependency and source:

```typescript
  const timetable = useMemo(() => {
    ...
    placeFiltered.forEach((e) => {
    ...
  }, [placeFiltered]);
```

Also change the `timetable.map(` source at line ~1175 to `placeFiltered.length ?` — the empty-state branch already lives on `filtered.length`; update the truthy branch:

Replace `) : filtered.length ? (` with `) : placeFiltered.length ? (`.

- [x] **Step 4: Pass the new props to `MapView`**

At line ~1359 replace:

```typescript
<MapView events={filtered} onSelect={selectEvent} language={language} />
```

with:

```typescript
<MapView
  events={filtered}
  onSelect={selectEvent}
  onSelectPlace={selectPlace}
  onClearPlace={clearPlace}
  language={language}
/>
```

- [x] **Step 5: Reset place on existing clear actions**

Make the "All" chip handler (line ~1051) also clear the place. Its handler body starts with `setTopic("");`. Add `setPlaceKeys(null);` as the first statement. Keep it minimal for Task 5; the full clear chip UI is Task 8.

- [x] **Step 6: Typecheck and build**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npx tsc --noEmit`
Expected: PASS (no unused-vars errors; `noUnusedLocals` is not set).
Then: `VITE_STATIC=1 npx vite build`
Expected: build succeeds.

- [x] **Step 7: Manual verification at the running server**

Run: `curl -s -o /dev/null -w "%{http_code}" 127.0.0.1:8765`
Expected: 200 (dev server serves `dist/` assets, so the rebuild reflects the new bundle).
Note: Manual click-through — clicking a cluster badge must freeze the side list to that place and zoom in; clicking bare map background must clear it.

- [x] **Step 8: Commit**

```bash
git add web/src/main.tsx
git commit -m "feat: selected-place state filters timetable from map drill-down"
```

---

## Task 6: Zoom-aware fit policy for cluster drill-down (optional simplification)

**Files:**
- Modify: `web/src/map-policy.mjs`
- Test: `web/src/map-policy.test.mjs`

This task is optional — the cluster click handler already calls `m.setView(pos, min(zoom+1, 19))` with animation, which is the full drill-down behaviour. Complete this task only if you want the initial fit and cluster jump to share a maxZoom policy; otherwise mark it skipped and move on. If done:

- [x] **Step 1: Add `maxDrillZoom`**

```javascript
export const MAX_DRIFT_ZOOM = 19;
export function shouldFitInitialMap({ hasFitted, coordinateCount }) {
  return !hasFitted && coordinateCount > 0;
}
```

(Constant added for centralisation; the cluster handler in Task 4 uses `Math.min(zoom + 1, 19)` — replace `19` with `MAX_DRIFT_ZOOM`.)

- [x] **Step 2: Test**

Add to `web/src/map-policy.test.mjs`:

```javascript
import { shouldFitInitialMap, MAX_DRIFT_ZOOM } from "./map-policy.mjs";
test("drill-down zoom is capped for tiles", () => {
  assert.equal(MAX_DRIFT_ZOOM, 19);
});
```

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npm test -- --test-name-pattern="map-policy"`
Expected: PASS.

- [x] **Step 3: Commit**

```bash
git add web/src/map-policy.mjs web/src/map-policy.test.mjs
git commit -m "refactor: centralise maximum drill-down zoom"
```

---

## Task 7: Cluster badge + clear-place chip styles

**Files:**
- Modify: `web/src/style.css:626-649` (near `.event-pin`)

- [x] **Step 1: Add cluster-badge and place-chip CSS**

Insert after the `.leaflet-marker-icon.event-pin > span` rule:

```css
.cluster-pin {
  background: none;
  border: none;
}
.cluster-pin > span {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--coral);
  color: #fff;
  border: 3px solid #fff;
  border-radius: 50%;
  width: 44px;
  height: 44px;
  box-shadow: 0 3px 10px #0b192c44;
  font: 700 13px "Plus Jakarta Sans", sans-serif;
}
.cluster-pin:hover > span {
  background: #e04a2c;
}
.place-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  padding: 8px 14px;
  border: 1px solid var(--coral);
  background: #fff4ef;
  color: #c0392b;
  white-space: nowrap;
}
.place-chip button {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 14px;
  line-height: 1;
  padding: 0;
  cursor: pointer;
}
```

- [x] **Step 2: Build**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && VITE_STATIC=1 npx vite build 2>&1 | tail -2`
Expected: build succeeds.

- [x] **Step 3: Commit**

```bash
git add web/src/style.css
git commit -m "style: cluster count badges and selected-place chip"
```

---

## Task 8: Clear-place chip UI + i18n strings

**Files:**
- Modify: `web/src/i18n.mjs` (en block ~100-130, de block ~305-325)
- Modify: `web/src/main.tsx` (filter-bar region ~1002-1064)
- Test: `web/src/i18n.test.mjs`

- [x] **Step 1: Add i18n keys**

English block — after `"results.areaCaption"`:

```javascript
    "results.places": "places",
    "results.placesDivider": "places ·",
    "map.clearPlace": "Show all locations",
```

German block — after `"results.areaCaption"` (German):

```javascript
    "results.places": "Orte",
    "results.placesDivider": "Orte /",
    "map.clearPlace": "Alle Orte anzeigen",
```

- [x] **Step 2: Test keys exist**

Append to `web/src/i18n.test.mjs`, inside the existing `for (const lang of ["en", "de"])` loop's key list, the new keys:

```javascript
    for (const key of ["nav.discover", "nav.sources", "nav.review", "filters.allTopics", "filters.allScales", "filters.freeOnly", "filters.semanticLoading", "filters.semanticReady", "filters.semanticFallback", "map.unknownLocation", "results.places", "results.placesDivider", "map.clearPlace"]) {
```

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npm test -- --test-name-pattern="i18n"`
Expected: PASS.

- [x] **Step 3: Update the caption in `main.tsx` to use the new keys**

In MapView, `tr` is not defined (it uses `t(language, key)` directly). Replace the literal German/English strings from Task 4 Step 4 with the new i18n keys:

```typescript
      <div className="map-caption">
        <span className="live-dot" /> {t(language, "results.areaCaption")}{" "}
        <span>
          {locationCount(events)} {t(language, "results.placesDivider")}{" "}
          {events.filter((e) => e.lat != null && e.lon != null).length}{" "}
          {t(language, "results.events")}
        </span>
      </div>
```

(Note: `results.events` already exists for both languages. The `place-chip` render in Step 4 below uses `tr`, which IS defined in the App component scope where that JSX lives.)

- [x] **Step 4: Render the clear-place chip in the filter bar**

In the `.filter-bar` row, immediately after the view-toggle block (line ~1047), insert:

```typescript
                  {placeKeys && (
                    <span className="place-chip">
                      <span className="material-symbols-outlined" aria-hidden="true">
                        place
                      </span>
                      {tr("map.clearPlace")}
                      <button aria-label={tr("map.clearPlace")} onClick={clearPlace}>
                        ×
                      </button>
                    </span>
                  )}
```

- [x] **Step 5: Typecheck, build, test**

Run:
```bash
cd /Users/agostontorok/Documents/code/nebenan/web
npx tsc --noEmit
VITE_STATIC=1 npx vite build 2>&1 | tail -2
npm test
curl -s -o /dev/null -w "%{http_code}\n" 127.0.0.1:8765
```
Expected: tsc PASS; build succeeds; `npm test` PASS; server 200.

- [x] **Step 6: Verify the rebuilt bundle carries the new symbols**

Run: `curl -s 127.0.0.1:8765/assets/index-*.js | rg -o "map.clearPlace|cluster-pin|place-chip" | sort | uniq -c`
Expected: at least one occurrence each of `cluster-pin` and `place-chip`.

- [x] **Step 7: Commit**

```bash
git add web/src/i18n.mjs web/src/i18n.test.mjs web/src/main.tsx
git commit -m "feat: clear-place chip and i18n for map location counts"
```

---

## Task 9: Regression pass

**Files:**
- None (verification only)

- [x] **Step 1: Run the entire web suite**

Run: `cd /Users/agostontorok/Documents/code/nebenan/web && npx tsc --noEmit && VITE_STATIC=1 npx vite build && npm test`
Expected: tsc PASS, build OK, `pass 27` (or more) and `fail 0`.

- [x] **Step 2: Run the entire Python suite**

Run: `cd /Users/agostontorok/Documents/code/nebenan && .venv/bin/python -m pytest tests -v 2>&1 | tail -5`
Expected: all pass.

- [x] **Step 3: Confirm the served bundle is current**

Run: `curl -s 127.0.0.1:8765/assets/index-*.js | rg -o "cluster-pin" | wc -l`
Expected: ≥ 1 (new bundle is what the dev server serves).

---

## Self-Review

**Spec coverage:**
- Geocode 61 streets now → Task 1-2. ✓
- Zoom-driven clustering to single events → Task 3-4 (groupEvents + cluster badge zoom). ✓
- List filters to selected place with clear chip → Task 5 + Task 8. ✓
- Caption true counts → Task 4 Step 5 + Task 8 Step 3. ✓
- Tests for grouping logic → Task 3 + Task 6. ✓
- Geocode/export sanity → Task 1-2. ✓

**Placeholder scan:** All steps carry concrete code or commands. ✓

**Type consistency:** `coordKey`, `groupEvents`, `locationCount`, `groupEvents` results (`{lat, lon, events}`), MapView props (`onSelectPlace: (keys: string[]) => void`), `placeKeys: string[] | null`, `placeFiltered` — all consistent across tasks. `MAX_DRIFT_ZOOM` only exists if Task 6 is taken. ✓