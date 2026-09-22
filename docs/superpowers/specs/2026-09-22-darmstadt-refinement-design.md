# Darmstadt Refinement Batch — Design

- **Date:** 2026-09-22
- **Status:** Approved (design review, 2026-09-22)
- **Scope:** One implementation plan. Seven independent, small-to-medium changes to the existing timetable web app.

## Context

The timetable app (FastAPI + Vite static site, published to GitHub Pages) has been through map clustering and geocoding work. This batch refines the user-facing behavior: the list shows what the map shows, the AI-extracted badge moves to the detail view, the area filter is removed in favor of the map, the map toggle moves to the right of the filter bar, the default language follows the browser, Simple Analytics is added, the repo is renamed `nahe`, and the site is restructured so the app lives at the URL `/nahe/darmstadt/` behind a city hub.

## Changes

### 1. AI-extracted tag moves to the detail view

- Remove the `ai-tag` span from the timetable list row (`web/src/main.tsx:1324-1328`).
- The detail panel already renders the `.ai-notice` card (flag link + warning, `main.tsx:1839-1854`) whenever `selected.ai_extracted`; keep it.
- Remove the now-unused `.ai-tag` CSS rule from `web/src/style.css`.
- Leave the `event.aiTitle`/`event.aiBadge` i18n keys in place (the detail view keeps `detail.aiTitle`).

### 2. The list always mirrors the map viewport

Replace place-key selection with viewport-derived visibility. The list shows exactly what the user can see on the map, plus all unmapped events (per user decision: unmapped events stay in the list — they can never be on a map).

**MapView (`web/src/main.tsx`, ~196-341):**

- Props change: drop `onSelectPlace`/`onClearPlace`; add `onMapVisible: (events: EventItem[]) => void` and `fitRequest: number`.
- Keep a ref to the latest `events` prop (`eventsRef`) and `onMapVisible` (`onMapVisibleRef`) so map-event listeners don't go stale.
- On `moveend` and `zoomend` (and once after the initial fit), compute:
  `visible = events.filter((e) => e.lat != null && e.lon != null && map.getBounds().contains([e.lat, e.lon]))`
  and call `onMapVisible(visible)`.
- Remove `m.on("click", () => onClearPlace?.())` (plain map click is now a no-op).
- Cluster click: replace `onSelectPlace(keys)` + `setView` with a drill-in fit:
  `m.fitBounds(L.latLngBounds(coords of g.events), { padding: [45, 45], maxZoom: MAX_DRIFT_ZOOM, animate: true })`.
  The resulting `moveend` triggers `onMapVisible`, narrowing the list to that cluster's events. Keep `MAX_DRIFT_ZOOM` import.
- Add a `fitRequest` effect: when it changes, re-run the same fit-to-all-bounds logic as the initial fit (`m.fitBounds(all coords, { padding: [45,45], maxZoom: 14 })`), used by the Reset / "All" controls.

**App (`web/src/main.tsx`, ~656-870, 1035-1163, 1385-1416):**

- Remove `placeKeys`, `setPlaceKeys`, `selectPlace` (useCallback), `clearPlace`, `placeFiltered`, and the `place-chip` render + its i18n usage.
- Add `[mapVisible, setMapVisible] = useState<EventItem[] | null>(null)` and `[fitRequest, setFitRequest] = useState(0)`.
- Add `isDesktop` from `window.matchMedia("(min-width: 761px)")`, kept fresh with a resize listener effect.
- `mapShown = isDesktop ? view === "split" : mobileMap` (matches the existing CSS: desktop hides the map in `list-only`, mobile shows it via `.show-map`).
- `listEvents = useMemo(...)`:
  - map shown and `mapVisible` non-null → `[...mapVisible, ...filtered.filter((e) => e.lat == null || e.lon == null)]`
  - otherwise → `filtered`
- Use `listEvents` everywhere `placeFiltered` was used (timetable memo + render branch, slots-pill count).
- Reset buttons (empty-state and "All" chip) drop `setPlaceKeys` and `setArea`, and bump `setFitRequest((n) => n + 1)`.

### 3. Simple Analytics

Add to `web/index.html` (per https://docs.simpleanalytics.com/script), anywhere in `<body>`:

```html
<!-- Simple Analytics - 100% privacy-first analytics -->
<script async src="https://scripts.simpleanalyticscdn.com/latest.js"></script>
```

SPA page views are auto-tracked by the script; no further wiring needed.

### 4. Remove the area filter

- Delete the `<select className="area-select">` block from the filter bar (`main.tsx:1040-1052`).
- Remove the `area` state, `byArea` line in the `filtered` memo (`main.tsx:787`), the `areas` memo (`main.tsx:870-872`), and every `setArea(...)` call (chips, Reset).
- Remove the `filters.area` i18n key from both language blocks in `web/src/i18n.mjs`.
- Remove `.area-select` CSS rules from `web/src/style.css` (including the `@media (max-width: 1050px)` `flex: 1` rule).

### 5. Map toggle moves to the right of the filter bar

- Move the `.view-toggle` div so it is the last child of `.filter-bar` (currently second, directly after the semantic-status element).
- Its behavior (toggles `view` split/list and the mobile `mobileMap`) is unchanged.

### 6. Default language follows the browser

- `web/src/i18n.mjs`: add exported `languageFromBrowser(stored)`:
  - stored `"de"` or `"en"` → that value (existing manual preference wins)
  - otherwise → `navigator.language` prefix `de` → `"de"`, else `"en"` (guard for non-browser environments)
- `web/src/main.tsx:659`: initial language state uses `languageFromBrowser(window.localStorage.getItem("darmstadt-language"))`.
- `web/src/i18n.test.mjs`: add a unit test for `languageFromBrowser` (stored pref wins, de browser → de, en/other browser → en).

### 7. Repo renamed to `nahe`; GitHub Pages serves a city hub at `/nahe/` with the app at `/nahe/darmstadt/`

Renamed repo `agostontorok/nebenan` → `agostontorok/nahe` (done during design review; local git remote updated). GitHub Pages project URLs follow the repo name, so the site root is now `https://agostontorok.github.io/nahe/`. No PAT or cross-repo push is needed — subfolders of the built site are served under the project path.

**Hub + city restructure (single repo, existing `pages.yml` unchanged):**

- `web/index.html` becomes a small static **hub** page ("nahe — local calendars"): brand mark, tagline, one city card linking to `darmstadt/`. Plain HTML/CSS in the existing pine/coral style; no React.
- The app moves to a Vite multi-page entry `web/darmstadt/index.html` — the same shell markup, same `/src/main.tsx` module — built to `dist/darmstadt/`. The current `index.html` app shell becomes the `darmstadt` entry.
- `web/vite.config.ts` gains `build.rollupOptions.input = { hub: web/index.html, darmstadt: web/darmstadt/index.html }`. `base: "./"` is unchanged; relative asset/math paths keep the app working from any sub-path, and `./data.json` resolves under the city path at runtime.
- `app/export_static.py` writes city data to `web/public/<city>/data.json` (default city `darmstadt`); the `DEFAULT_OUT` path changes accordingly, and the workflow's `python -m app.export_static` step is unchanged (defaults to `darmstadt`).
- The app's tab routing uses only React state (no `location.pathname`), so no router change.

**URLs after deploy:** `/nahe/` → hub; `/nahe/darmstadt/` → app. Future cities (e.g. `paris`) = new `web/<city>/index.html` entry + `web/public/<city>/data.json` + hub card; no workflow change.

**Brand updates for the rename:**

- `web/src/main.tsx:26,28` — GitHub issue-template URLs become `https://github.com/agostontorok/nahe/issues/...`.
- `web/src/main.tsx:932` — header brand `nebenan<span class="brand-city">DARMSTADT</span>` → `nahe<span class="brand-city">DARMSTADT</span>`.
- `web/src/main.tsx:1746` — footer brand mark `nebenan` → `nahe`.
- New hub page uses `nahe` as its wordmark.

**Local preview** (`127.0.0.1:8765`, serves `web/dist`): root becomes the hub, app preview at `/darmstadt/`.

## Non-goals

- No visual/UX redesign of markers beyond existing cluster styling.
- No change to `/api` behavior. Local preview stays on the dev server but its root becomes the city hub; the app preview is at `/darmstadt/`.
- No data/geocoding changes; only the `export_static` output path moves under `web/public/<city>/`.

## Testing

- `cd web && npm test` — keep 37 passing. Update `src/i18n.test.mjs`: remove `map.clearPlace` from the required-key list (the key is deleted in change 2 alongside the place-chip) and add `languageFromBrowser` cases (stored pref wins; `de` browser → `de`; `en`/other → `en`). No new module test files needed.
- `cd web && npx tsc --noEmit` — clean.
- `VITE_STATIC=1 npx vite build` — succeeds; `web/dist/` contains the hub `index.html` and a `darmstadt/` subfolder; regenerated `web/dist` serves at `127.0.0.1:8765` (hub at `/`, app at `/darmstadt/`) for local preview.
- `.venv/bin/python -m pytest tests -q` — unaffected (no server changes); plus a run of `python -m app.export_static` to confirm the new `web/public/darmstadt/data.json` output.
- Grep checks: no remaining `placeKeys`, `selectPlace` (as a map prop), `placeFiltered`, `setArea`, `area-select`, `map.clearPlace` references; remaining `nebenan` instances are only the report link text/title casing if other than the renamed brand.