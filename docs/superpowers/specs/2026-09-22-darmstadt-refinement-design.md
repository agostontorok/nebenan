# Darmstadt Refinement Batch — Design

- **Date:** 2026-09-22
- **Status:** Approved (design review, 2026-09-22)
- **Scope:** One implementation plan. Seven independent, small-to-medium changes to the existing timetable web app.

## Context

The timetable app (FastAPI + Vite static site, published to GitHub Pages) has been through map clustering and geocoding work. This batch refines the user-facing behavior: the list shows what the map shows, the AI-extracted badge moves to the detail view, the area filter is removed in favor of the map, the map toggle moves to the right of the filter bar, the default language follows the browser, Simple Analytics is added, and GitHub Pages serves the app at `nebenan/darmstadt`.

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

### 7. GitHub Pages serves the app at `nebenan/darmstadt`

Target URL: `https://agostontorok.github.io/nebenan/darmstadt/` via the user-pages repo `agostontorok/agostontorok.github.io` (branch `master`, exists).

- Rewrite `.github/workflows/pages.yml`:
  - Keep the existing build steps (Python tests + `export_static`, `npm ci`, `VITE_STATIC=1 npm run build`).
  - Replace `actions/configure-pages` + `upload-pages-artifact` + `deploy-pages` with a cross-repo publish of `web/dist` into `agostontorok.github.io` at `nebenan/darmstadt/`.
  - Use `peaceiris/actions-gh-pages@v4` with `personal_token: ${{ secrets.GH_PAGES_TOKEN }}`, `publish_dir: web/dist`, `destination_dir: nebenan/darmstadt`, `publish_branch: master`, `keep_files: true` (preserve anything else already on the user-pages site).
- `web/vite.config.ts` already uses `base: "./"`; the static site (including `./data.json` fetches and tab-based routing with no `location.pathname` use) works from any sub-path. No Vite change.
- **Prerequisite (blocker):** no repo secrets exist today. The current deployment works only because the native `deploy-pages` action needs no secret. Cross-repo push needs a new PAT secret:
  - Create a fine-grained or classic PAT scoped to `agostontorok.github.io` (contents read/write).
  - Add it as the repo secret `GH_PAGES_TOKEN` (owner has admin rights on this repo).
  - Until that secret exists, the build steps run but the publish step fails; the old bare `/nebenan/` project Pages remains live until the user disables it in Pages settings.

## Non-goals

- No visual/UX redesign of markers beyond existing cluster styling.
- No change to `/api` behavior or the local dev server mount path (local preview keeps working at `/`; the GH Pages address is handled by the workflow).
- No data/geocoding changes.

## Testing

- `cd web && npm test` — keep 37 passing. Update `src/i18n.test.mjs`: remove `map.clearPlace` from the required-key list (key is deleted in change 5) and add `languageFromBrowser` cases (stored pref wins; `de` browser → `de`; `en`/other → `en`). No new module test files needed.
- `cd web && npx tsc --noEmit` — clean.
- `VITE_STATIC=1 npx vite build` — succeeds; regenerated `web/dist` serves at `127.0.0.1:8765` for local preview.
- `.venv/bin/python -m pytest tests -q` — unaffected (no server changes).
- Grep check: no remaining `placeKeys`, `selectPlace`, `onSelectPlace`, `placeFiltered`, `setArea`, `area-select`, `map.clearPlace` references.