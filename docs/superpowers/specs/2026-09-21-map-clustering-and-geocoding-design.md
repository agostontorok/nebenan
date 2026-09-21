# Map Clustering and Geocoding — Design

Date: 2026-09-21

## Problem

The timetable map is sparse and misleads:

- Only **135 of 2118** published events have coordinates, collapsing into just **15 distinct coordinate pairs** (max 44 events per pair).
- The pin labels are the event's array index (`i + 1`), not a count. Events sharing a coordinate stack, and the topmost marker shows a large index like "300" — implying 300 events at one point when there are at most 44.
- 1983 events have no lat/lon at all. Of those, **1629 have a `venue` string and 554 have an `address`**. Extracting street addresses from `address` yields **61 unique streets** covering **438 events**.

## Goals

1. Populate the map by geocoding the 61 unique street addresses now.
2. Replace stacking markers with zoom-driven clustering: click a big number → zoom in to the next level → differentiate 2–3 → down to single events.
3. Side list filters to the events at the selected place on every drill-down step.
4. Map caption shows true counts ("X locations / Y events").
5. Verify cluster grouping logic with tests.

## Non-goals

- Geocoding venues by name (only explicit street+number addresses are resolved — the existing `street_address` policy).
- Geocoding address-free events (the 1983 include ~1450 with neither street nor address).
- Auto-geocoding on the client. Geocoding stays a server-side pipeline step.

## Approach (chosen)

Process: **A. Run geocode now**; then optional **B. batch backfill**; **C.** cluster on the client with a lightweight zoom-level grid (no new npm dependency).

## Geocoding

- Existing pipeline: `Collector.geocode(limit=20)` in `app/collect.py` resolves `address` → street+number via `street_address` (regex), queries Nominatim serially with a 1.1s sleep, caches by `street, city` in the `geocache` table. Only 20 attempts per run, which is why mapping lags far behind.
- Now: run until the cache warms for all 61 streets (~70s). Then re-run `app/export_static.py` `main()` so `web/public/data.json` (the static bundle the browser/editor serve) includes the new `lat`/`lon`/`coordinate_evidence`.
- Deterministic: the pipeline's `local_coordinates()` keeps results within the Darmstadt bounding box; exact duplicates share one coordinate pair by design.

## Clustering UX (client, `web/src/main.tsx` map component)

- Replace the per-event `L.marker` loop with a cluster render pass over `events`:
  - At the current zoom, bin events by grid cell (coordinate rounded to a cell size that shrinks as zoom increases).
  - Cell with 1 event → existing single pin (opens the event).
  - Cell with 2+ → count badge (divIcon bubble showing the number; larger bubble for larger counts).
  - Recompute on `zoomend` / `moveend`; no full marker churn.
- Badge click → move one zoom level closer to the badge's members and select the place. Nearby-but-distinct venues separate level by level until singles remain.
- Same-address events (many share one coordinate) can never separate geographically — for those, the drill-down reveals them through the **side list** (nothing on the map distinguishes them beyond the count).
- **List sync (user-confirmed):** clicking a cluster sets a "selected place" filter on the timetable showing exactly that place's events, exposed as a clearable chip. Clicking the map background clears it and restores the full list. Pin click on a single event keeps today's open-event behavior.
- **Map caption** becomes `<locations> Orte / <events> Termine` ("X places / Y events") using distinct coordinates vs event count.

## Data flow

```
app/collect.py geocode (loop ≥ all 61 streets)
  → app/export_static.py main() → web/public/data.json
  → VITE_STATIC=1 npx vite build   (dev server serves built dist/ assets)
  → Map component renders clusters from events[]
```

## Testing

- Cluster grouping logic as pure functions:
  - cell binning shrinks as zoom increases,
  - identical-coordinate members stay in one cell at all zooms,
  - nearby distinct coordinates separate at deeper zooms,
  - single-event cells produce a pin, multi-event cells produce a count badge.
- Geocode/export sanity: piping a small set of address rows through `street_address` → cache → export yields coordinates in `data.json`.

## Open follow-ups (not in this change)

- Venue-only events (1629 have a venue but ~1450 have neither street in `address` nor coords) remain unmapped.
- The 4.9 MB `data/events.sqlite` and the geocache growth are still uncommitted.