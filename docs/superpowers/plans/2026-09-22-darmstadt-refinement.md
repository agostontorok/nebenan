# Darmstadt Refinement Batch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seven refinements shipped together: the event list mirrors the map viewport, the AI-extracted tag moves to the event detail, the area filter is replaced by the map, the map toggle moves to the right of the filter bar, the language defaults from the browser, Simple Analytics is added, and the site becomes a city hub (`nahe`) with the app at `/darmstadt/`.

**Architecture:** The repo was renamed `agostontorok/nebenan` → `agostontorok/nahe` (done; remote updated). GitHub Pages project URLs follow the repo name, so we keep the single-repo deploy and restructure the Vite build into a multi-page site: a static hub at the root and the existing React app as a second entry under `web/darmstadt/`. Place-key filtering is removed entirely and replaced by a viewport-driven callback from Leaflet (`moveend`/`zoomend`) so the timetable always shows exactly the mapped events inside the current map bounds plus unmapped events.

**Tech Stack:** React (no router — tab state only), Vite multi-page, Leaflet, plain CSS, FastAPI static export to `web/public/<city>/data.json`, GitHub Actions Pages deploy.

**Working context for the engineer:**
- The local dev server (uvicorn PID 54820) runs at `127.0.0.1:8765` serving the **built** `web/dist/` — never kill it. After every web change rebuild with `VITE_STATIC=1 npx vite build` (from `web/`) for the preview to update.
- Work happens on `main`. The user reviews visually between tasks; there is no screenshot tooling.
- Verify commands (used across tasks):
  - `cd web && npm test` → 37 passing today; count changes with i18n edits.
  - `cd web && npx tsc --noEmit` → clean.
  - `cd /Users/agostontorok/Documents/code/nebenan && .venv/bin/python -m pytest tests -q` → 99 passed (ignore the known fastapi `DeprecationWarning`).
  - `curl -s -o /dev/null -w "%{http_code}" 127.0.0.1:8765` → 200.
- `web/public/data.json` (4.5 MB) is gitignored and must stay untracked. `data/events.sqlite` is also untracked — never commit it.
- **Do not** use `git mv` on `web/index.html`; it gets overwritten with hub content in Task 6.

---

### Task 1: i18n — add `languageFromBrowser`

**Files:**
- Modify: `web/src/i18n.mjs` (add function after `languageFromStorage` ~line 5)
- Modify: `web/src/i18n.test.mjs` (import + tests)

- [ ] **Step 1: Update the existing test file first**

Edit `web/src/i18n.test.mjs`:

```js
import { languageFromBrowser, languageFromStorage, copy, topicLabels, scaleLabels } from "./i18n.mjs";
```

Then append:

```js
test("languageFromBrowser uses stored preference before browser language", () => {
  assert.equal(languageFromBrowser("de"), "de");
  assert.equal(languageFromBrowser("en"), "en");
  assert.equal(languageFromBrowser("fr"), "en");
  assert.equal(languageFromBrowser(null), "en");
});

test("languageFromBrowser falls back to the browser language", () => {
  const original = globalThis.navigator;
  try {
    globalThis.navigator = { language: "de-DE" };
    assert.equal(languageFromBrowser(null), "de");
    globalThis.navigator = { language: "en-US" };
    assert.equal(languageFromBrowser(null), "en");
    globalThis.navigator = { language: "fr-FR" };
    assert.equal(languageFromBrowser(null), "en");
  } finally {
    globalThis.navigator = original;
  }
});
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `cd web && npm test`
Expected: FAIL — `languageFromBrowser is not a function` (import undefined).

- [ ] **Step 3: Implement in `web/src/i18n.mjs`**

Add right after `languageFromStorage` (line 5):

```js
export function languageFromBrowser(stored) {
  if (stored === "de" || stored === "en") return stored;
  const nav =
    typeof navigator !== "undefined" && navigator.language
      ? navigator.language.toLowerCase()
      : "";
  return nav.startsWith("de") ? "de" : "en";
}
```

(Do **not** delete any i18n keys in this task; `filters.area` and `map.clearPlace` are still rendered by the UI and are removed together with their UI in Task 4.)

- [ ] **Step 4: Run tests**

Run: `cd web && npm test`
Expected: PASS — 39 passing, 0 failing (37 existing + 2 new).

- [ ] **Step 5: Verify types and build**

Run: `cd web && npx tsc --noEmit && VITE_STATIC=1 npx vite build`
Expected: tsc clean; build succeeds in ~2s.

- [ ] **Step 6: Commit**

```bash
git add web/src/i18n.mjs web/src/i18n.test.mjs
git commit -m "feat: default language from browser; drop dead area/place keys"
```

---

### Task 2: MapView — report viewport-visible events instead of place selection

**Files:**
- Modify: `web/src/main.tsx` MapView (`~196-341`)

- [ ] **Step 1: Change the props signature**

Replace lines `196-208`:

```tsx
function MapView({
  events,
  onSelect,
  onMapVisible,
  fitRequest,
  language,
}: {
  events: EventItem[];
  onSelect: (e: EventItem) => void;
  onMapVisible: (events: EventItem[]) => void;
  fitRequest: number;
  language: "en" | "de";
}) {
```

- [ ] **Step 2: Add refs for the live `events` prop and the callback**

Replace lines `209-215`:

```tsx
  const ref = useRef<HTMLDivElement>(null),
    map = useRef<L.Map | null>(null),
    layer = useRef<L.LayerGroup | null>(null),
    hasFitted = useRef(false),
    userInteracted = useRef(false);
  const eventsRef = useRef(events);
  const onMapVisibleRef = useRef(onMapVisible);
  eventsRef.current = events;
  onMapVisibleRef.current = onMapVisible;
  const reportVisible = useRef<() => void>(() => {});
  const [tileError, setTileError] = useState(false);
  const [zoom, setZoom] = useState(13);
```

- [ ] **Step 3: Wire up the report listener in the init effect**

In the init effect, replace the two lines

```tsx
    m.on("dragstart zoomstart", () => {
      if (hasFitted.current) userInteracted.current = true;
    });
    m.on("click", () => onClearPlace?.());
    m.on("zoomend", () => setZoom(m.getZoom()));
```

with

```tsx
    m.on("dragstart zoomstart", () => {
      if (hasFitted.current) userInteracted.current = true;
    });
    reportVisible.current = () => {
      const m2 = map.current;
      if (!m2) return;
      const b = m2.getBounds();
      const visible = eventsRef.current.filter(
        (e) => e.lat != null && e.lon != null && b.contains([e.lat, e.lon]),
      );
      onMapVisibleRef.current(visible);
    };
    m.on("moveend zoomend", () => {
      setZoom(m.getZoom());
      reportVisible.current();
    });
```

- [ ] **Step 4: Change the cluster click to a drill-in fit**

In the render effect, replace the cluster marker click handler (lines `295-301`):

```tsx
        .on("click", () => {
          const keys = (g.events as EventItem[]).map((e) =>
            coordKey(e.lat!, e.lon!),
          );
          onSelectPlace?.(keys);
          m.setView(pos, Math.min(zoom + 1, MAX_DRIFT_ZOOM), { animate: true });
        })
```

with

```tsx
        .on("click", () => {
          const clusterBounds = L.latLngBounds(
            (g.events as EventItem[]).map(
              (e) => [e.lat!, e.lon!] as L.LatLngTuple,
            ),
          );
          m.fitBounds(clusterBounds, {
            padding: [45, 45],
            maxZoom: MAX_DRIFT_ZOOM,
            animate: true,
          });
        })
```

- [ ] **Step 5: Report visible events after the initial fit**

In the render effect, inside the `shouldFitInitialMap` block (lines `304-315`), add the report after the fit:

```tsx
    if (
      shouldFitInitialMap({
        hasFitted: hasFitted.current || userInteracted.current,
        coordinateCount: coords.length,
      })
    ) {
      hasFitted.current = true;
      m.fitBounds(L.latLngBounds(coords), {
        padding: [45, 45],
        maxZoom: 14,
      });
      reportVisible.current();
    }
```

- [ ] **Step 6: Update the render-effect dependency array**

Change `}, [events, onSelect, onSelectPlace, language, zoom]);` to `}, [events, onSelect, language, zoom]);`

- [ ] **Step 7: Add the `fitRequest` reset effect**

Add directly after the render effect (after line ~316), before the `return` JSX:

```tsx
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const coords: L.LatLngTuple[] = [];
    groupEvents(eventsRef.current, 13).forEach((g) => {
      coords.push([g.lat, g.lon]);
    });
    if (!coords.length) return;
    m.fitBounds(L.latLngBounds(coords), {
      padding: [45, 45],
      maxZoom: 14,
    });
    hasFitted.current = true;
    reportVisible.current();
  }, [fitRequest]);
```

- [ ] **Step 8: Verify**

Run: `cd web && npx tsc --noEmit && npm test && VITE_STATIC=1 npx vite build`
Expected: tsc clean, 39 npm tests pass, build succeeds.
Note: tsc will still pass because the App still passes the old props today (extra props are allowed by structural typing only if the target accepts them — the App currently passes `onSelectPlace`/`onClearPlace` which no longer exist, so **tsc will error here**. That is expected until Task 4 wires the new props.)

- [ ] **Step 9: Commit (skipped if tsc errors — proceed to Task 3/4 and commit after wiring)**

If tsc errors only because of the not-yet-updated App props, do NOT commit here; continue to Task 4 and commit at the end of Task 4. If tsc is already clean, commit with:

```bash
git add web/src/main.tsx
git commit -m "feat: map reports viewport-visible events; clusters drill-in via fit"
```

---

### Task 3: App — replace place filtering with viewport list

**Files:**
- Modify: `web/src/main.tsx` (language init, state, memos, `filtered`, imports)

- [ ] **Step 1: Update the i18n import and `coordKey` import**

Line 9: `import { coordKey, groupEvents, locationCount } from "./map-clusters.mjs";` → `import { groupEvents, locationCount } from "./map-clusters.mjs";`

Lines 17-21: replace `languageFromStorage,` with `languageFromBrowser,`:

```tsx
import {
  languageFromBrowser,
  scaleLabels as scaleLabelsByLanguage,
  topicLabels as topicLabelsByLanguage,
  t,
} from "./i18n.mjs";
```

- [ ] **Step 2: Use the browser-aware language initializer**

Replace lines `657-663`:

```tsx
    [language, setLanguage] = useState<"en" | "de">(() => {
      try {
        return languageFromStorage(window.localStorage.getItem("darmstadt-language"));
      } catch {
        return "en";
      }
    }),
```

with

```tsx
    [language, setLanguage] = useState<"en" | "de">(() => {
      try {
        return languageFromBrowser(
          window.localStorage.getItem("darmstadt-language"),
        );
      } catch {
        return "en";
      }
    }),
```

- [ ] **Step 3: Remove the `area` and `placeKeys` state; add map/list state**

Delete line 676 `[area, setArea] = useState(""),`.
Delete line 682 `[placeKeys, setPlaceKeys] = useState<string[] | null>(null),`.

After line 683 (`[timeVenue, setTimeVenue] = useState<"time" | "venue">("time"),`) add:

```tsx
    [mapVisible, setMapVisible] = useState<EventItem[] | null>(null),
    [fitRequest, setFitRequest] = useState(0),
```

- [ ] **Step 4: Add an `isDesktop` state + resize listener**

Add after the `view` state declaration (line 684):

```tsx
    [isDesktop, setIsDesktop] = useState(() =>
      window.matchMedia("(min-width: 761px)").matches,
    ),
```

Then, in the existing `useEffect` that syncs language/localStorage (the one that sets `document.documentElement.lang`), no change. Add a separate effect after line 707:

```tsx
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 761px)");
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
```

- [ ] **Step 5: Drop the area branch from the `filtered` memo**

Replace lines `782-791`:

```tsx
  const filtered = useMemo(() => {
    const base =
      !query.trim() || !semanticScores
        ? lexicalFiltered
        : (rankSemanticMatches(baseFiltered, query, semanticScores) as EventItem[]);
    const byArea = area ? base.filter((e) => e.area === area) : base;
    return evening
      ? byArea.filter((e) => hourOf(e.start) >= 18)
      : byArea;
  }, [baseFiltered, lexicalFiltered, query, semanticScores, area, evening]);
```

with

```tsx
  const filtered = useMemo(() => {
    const base =
      !query.trim() || !semanticScores
        ? lexicalFiltered
        : (rankSemanticMatches(baseFiltered, query, semanticScores) as EventItem[]);
    return evening
      ? base.filter((e) => hourOf(e.start) >= 18)
      : base;
  }, [baseFiltered, lexicalFiltered, query, semanticScores, evening]);
```

- [ ] **Step 6: Replace `selectPlace`/`clearPlace`/`placeFiltered` with `listEvents`**

Replace lines `829-836`:

```tsx
  const selectEvent = React.useCallback((e: EventItem) => setSelected(e), []);
  const selectPlace = React.useCallback((keys: string[]) => setPlaceKeys(keys), []);
  const clearPlace = React.useCallback(() => setPlaceKeys(null), []);
  const placeFiltered = useMemo(() => {
    if (!placeKeys) return filtered;
    const keySet = new Set(placeKeys);
    return filtered.filter((e) => e.lat != null && e.lon != null && keySet.has(coordKey(e.lat, e.lon)));
  }, [filtered, placeKeys]);
```

with

```tsx
  const selectEvent = React.useCallback((e: EventItem) => setSelected(e), []);
  const mapShown = isDesktop ? view === "split" : mobileMap;
  const listEvents = useMemo(() => {
    if (mapShown && mapVisible)
      return [
        ...mapVisible,
        ...filtered.filter((e) => e.lat == null || e.lon == null),
      ];
    return filtered;
  }, [mapShown, mapVisible, filtered]);
```

- [ ] **Step 7: Remove the `areas` memo**

Delete lines `870-874`:

```tsx
  const areas = useMemo(
    () =>
      [...new Set(events.map((e) => e.area).filter(Boolean) as string[])],
    [events],
  );
```

- [ ] **Step 8: Point the timetable at `listEvents`**

In the timetable memo (lines `880-903`) change `placeFiltered.forEach((e) => {` → `listEvents.forEach((e) => {` and the dependency array `}, [placeFiltered]);` → `}, [listEvents]);`.

- [ ] **Step 9: Verify types only**

Run: `cd web && npx tsc --noEmit`
Expected: tsc errors ONLY at the MapView call site (old props) and anywhere still referencing the removed names. Resolve those in Task 4.

---

### Task 4: App UI — filter bar, controls, and map wiring

**Files:**
- Modify: `web/src/main.tsx` (filter bar `~1039-1163`, schedule UI, empty-state Reset, MapView usage, ai-tag)

- [ ] **Step 1: Remove the area `<select>`**

Delete lines `1040-1052` (the whole `<select className="area-select">…</select>` block).

- [ ] **Step 2: Remove the `place-chip` block**

Delete only the `{placeKeys && (` … `)}` block (lines `1085-1095`). The `<span className="chip-divider" aria-hidden="true" />` on line 1096 stays (it separates the semantic status from the chips).

- [ ] **Step 3: Fix the "All" chip handler**

In the All chip `onClick` (lines `1097-1113`), remove `setPlaceKeys(null);` and `setArea("");`, and add the fit bump. The handler becomes:

```tsx
                    onClick={() => {
                      setTopic("");
                      setScale("");
                      setFree(false);
                      setEvening(false);
                      setQuery("");
                      chooseMode("week");
                      setView("split");
                      setMobileMap(false);
                      setFitRequest((n) => n + 1);
                    }}
```

- [ ] **Step 4: Move the `.view-toggle` to the end of the filter bar**

Cut the whole `<div className="view-toggle" role="group" aria-label={tr("filters.split")}>…</div>` block (lines `1066-1084`) and paste it as the **last child** of `.filter-bar` — after the Culture chip button (which ends at line `1162`). The resulting filter-bar DOM order is: semantic-status, chip-divider, All, Now, Tonight, Music, Sports, Culture, view-toggle.

- [ ] **Step 5: Point the results bar and empty state at `listEvents`**

- Line 1192: `{loading ? "…" : placeFiltered.length} {tr("schedule.slots")}` → `{loading ? "…" : listEvents.length} {tr("schedule.slots")}`
- Line 1223: `) : placeFiltered.length ? (` → `) : listEvents.length ? (`

- [ ] **Step 6: Fix the empty-state Reset button**

In the empty-state Reset `onClick` (lines `1390-1401`), remove `setPlaceKeys(null);` and `setArea("");`, and add the fit bump:

```tsx
                        onClick={() => {
                          setQuery("");
                          setTopic("");
                          setScale("");
                          setFree(false);
                          setEvening(false);
                          setView("split");
                          setMobileMap(false);
                          chooseMode("week");
                          setFitRequest((n) => n + 1);
                        }}
```

- [ ] **Step 7: Wire the new MapView props**

Replace lines `1409-1415`:

```tsx
                  <MapView
                    events={filtered}
                    onSelect={selectEvent}
                    onSelectPlace={selectPlace}
                    onClearPlace={clearPlace}
                    language={language}
                  />
```

with

```tsx
                  <MapView
                    events={filtered}
                    onSelect={selectEvent}
                    onMapVisible={setMapVisible}
                    fitRequest={fitRequest}
                    language={language}
                  />
```

- [ ] **Step 8: Remove the AI tag from the list row**

Delete lines `1324-1328`:

```tsx
                                    {e.ai_extracted && (
                                      <span className="ai-tag" title={tr("event.aiTitle")}>
                                        {tr("event.aiBadge")}
                                      </span>
                                    )}
```

The `.ai-notice` block in the detail panel (lines `1839-1854`) is untouched.

- [ ] **Step 9: Delete the now-unused i18n keys**

The UI references are gone; remove the four key lines from `web/src/i18n.mjs` (each lang block keeps its siblings — just drop the four lines):

- `"filters.area": "All Darmstadt Areas",` (en `~62`)
- `"filters.area": "Alle Darmstädter Bezirke",` (de `~270`)
- `"map.clearPlace": "Show all locations",` (en `~120`)
- `"map.clearPlace": "Alle Orte anzeigen",` (de `~328`)

In `web/src/i18n.test.mjs`, remove `"map.clearPlace"` from the required-key array in the completeness test (the array is unchanged otherwise).

- [ ] **Step 10: Verify**

Run: `cd web && npx tsc --noEmit && npm test && VITE_STATIC=1 npx vite build`
Expected: tsc clean; **38 npm tests pass** (baseline 37 → +2 languageFromBrowser tests in Task 1 → −1 key-list entry here); build succeeds.

- [ ] **Step 11: Commit**

```bash
git add web/src/main.tsx web/src/i18n.mjs web/src/i18n.test.mjs
git commit -m "feat: list mirrors map viewport; drop area and place filters"
```

---

### Task 5: Brand — rename to `nahe` (logo + links)

**Files:**
- Modify: `web/src/main.tsx` (issue URLs, header brand, footer brand)

- [ ] **Step 1: Update issue-template URLs**

Lines `25-28`:

```tsx
export const SHARE_URL =
  "https://github.com/agostontorok/nahe/issues/new?template=event-share.yml";
export const FLAG_URL =
  "https://github.com/agostontorok/nahe/issues/new?template=event-flag.yml";
```

- [ ] **Step 2: Update the header brand wordmark**

Line 932: `nebenan<span className="brand-city">DARMSTADT</span>` → `nahe<span className="brand-city">DARMSTADT</span>`

The `brand-mark` monogram `n<span>•</span>` on lines 929-931 stays as-is (the `n` initials "nahe").

- [ ] **Step 3: Update the footer brand**

Line 1746: `nebenan<span>•</span>` → `nahe<span>•</span>`

- [ ] **Step 4: Verify**

Run: `cd web && npx tsc --noEmit && VITE_STATIC=1 npx vite build`
Expected: tsc clean, build ok.

- [ ] **Step 5: Commit**

```bash
git add web/src/main.tsx
git commit -m "feat: rename brand and links to nahe"
```

---

### Task 6: Hub + city restructure

**Files:**
- Modify: `app/export_static.py` (default output path)
- Modify: `.gitignore` (city data path)
- Modify: `web/vite.config.ts` (multi-page input)
- Create: `web/darmstadt/index.html` (app shell + analytics)
- Replace: `web/index.html` (hub page + analytics)

- [ ] **Step 1: Point the static export at the city path**

`app/export_static.py` line 8:

```python
DEFAULT_OUT = ROOT / 'web/public/darmstadt/data.json'
```

(Explicit-path callers in `tests/test_export_static.py` pass their own `out`, so no pytest change is needed.)

Run: `cd /Users/agostontorok/Documents/code/nebenan && .venv/bin/python -m pytest tests/test_export_static.py -q`
Expected: 5 passed.

- [ ] **Step 2: Keep the city data file untracked**

In `.gitignore`, replace the exact rule `web/public/data.json` with a wildcard covering every city:

```
web/public/*/data.json
```

Then confirm both old and new paths are ignored:

Run: `cd /Users/agostontorok/Documents/code/nebenan && git check-ignore web/public/data.json web/public/darmstadt/data.json`
Expected: both paths printed (exit 0).

- [ ] **Step 3: Multi-page Vite config**

Replace `web/vite.config.ts` entirely:

```ts
import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "./",
  build: {
    rollupOptions: {
      input: {
        hub: resolve(__dirname, "index.html"),
        darmstadt: resolve(__dirname, "darmstadt/index.html"),
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
```

- [ ] **Step 4: Create the city entry `web/darmstadt/index.html`**

Create the directory and file. Content (same app shell as the old root, plus the analytics snippet and `nahe` title):

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#0b192c" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
      rel="stylesheet"
    />
    <meta
      name="description"
      content="Discover local events in Darmstadt and its neighbouring towns, collected transparently and shown on a map."
    />
    <title>nahe · Discover Darmstadt</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
    <!-- Simple Analytics - 100% privacy-first analytics -->
    <script async src="https://scripts.simpleanalyticscdn.com/latest.js"></script>
  </body>
</html>
```

- [ ] **Step 5: Replace the hub `web/index.html`**

Overwrite `web/index.html` with the hub page (includes the Simple Analytics snippet, consistent with the docs at https://docs.simpleanalytics.com/script):

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#0b192c" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;700;800&display=swap"
      rel="stylesheet"
    />
    <meta
      name="description"
      content="nahe — local calendars for the places you live in."
    />
    <title>nahe · local calendars</title>
    <style>
      :root {
        --pine: #0b192c;
        --paper: #fdfbf7;
        --coral: #ff5733;
      }
      * {
        box-sizing: border-box;
      }
      body {
        margin: 0;
        font-family: "Plus Jakarta Sans", system-ui, sans-serif;
        background: var(--paper);
        color: var(--pine);
      }
      .hub {
        min-height: 100vh;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 14px;
        padding: 24px;
        text-align: center;
      }
      .wordmark {
        margin: 0;
        font-size: 40px;
        font-weight: 800;
        letter-spacing: 0.02em;
      }
      .wordmark b {
        color: var(--coral);
      }
      .tagline {
        margin: 0;
        color: #5a6779;
      }
      .cities {
        display: flex;
        gap: 14px;
        margin-top: 26px;
        flex-wrap: wrap;
        justify-content: center;
      }
      .card {
        display: flex;
        align-items: center;
        padding: 16px 22px;
        border: 1px solid #dfe2e8;
        border-radius: 14px;
        background: #fff;
        color: var(--pine);
        text-decoration: none;
        font-weight: 700;
        transition:
          transform 0.12s ease,
          box-shadow 0.12s ease;
      }
      .card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(11, 25, 44, 0.1);
      }
    </style>
  </head>
  <body>
    <div class="hub">
      <p class="wordmark">na<b>he</b></p>
      <p class="tagline">Local calendars for the places around you.</p>
      <div class="cities">
        <a class="card" href="darmstadt/">Darmstadt</a>
      </div>
    </div>
    <!-- Simple Analytics - 100% privacy-first analytics -->
    <script async src="https://scripts.simpleanalyticscdn.com/latest.js"></script>
  </body>
</html>
```

- [ ] **Step 6: Generate the city data and rebuild**

Run:
```bash
cd /Users/agostontorok/Documents/code/nebenan && PYTHONPATH=. .venv/bin/python -m app.export_static
cd web && VITE_STATIC=1 npx vite build
```
Expected: `web/public/darmstadt/data.json` created; `web/dist/` contains `index.html`, `darmstadt/index.html`, `darmstadt/data.json` and `assets/`.

Verify locally:
```bash
curl -s 127.0.0.1:8765/ | grep -c "<title>nahe · local calendars</title>"
curl -s 127.0.0.1:8765/darmstadt/ | grep -c '<div id="root"></div>'
```
Expected: `1` for both (the app HTML has the root div; the hub does not).

Also run: `cd web && npm test && npx tsc --noEmit`
Expected: tests pass, tsc clean.

Note: the old gitignored `web/public/data.json` (4.5 MB) at the root is now stale — leave it in place (untracked); it is not referenced by either entry anymore.

- [ ] **Step 7: Commit**

```bash
git add app/export_static.py .gitignore web/vite.config.ts web/darmstadt/index.html web/index.html
git commit -m "feat: city hub at root with app under /darmstadt/; add Simple Analytics"
```

---

### Task 7: CSS cleanups

**Files:**
- Modify: `web/src/style.css`

- [ ] **Step 1: Remove dead rules**

Delete these blocks/rules from `web/src/style.css`:
- `.event-tags .ai-tag {` block (`~543`) if it exists (verify; the parent `.tt-tags` may not use it — only shown as matched earlier).
- `.place-chip {` (`~692`) and `.place-chip button {` (`~705`) — both blocks.
- `.area-select {` (`~1589`) — the whole rule.
- The `.ai-tag,` (`~1896`) and `.ai-tag {` (`~1906`) rules — both blocks.
- Inside `@media (max-width: 1050px)` (`~2001`): `.area-select { flex: 1; }`.

Leave `.chip-divider`, `.view-toggle`, `.filter-bar`, and the `.list-only`/`.show-map` rules untouched.

- [ ] **Step 2: Verify**

Run: `cd web && npx tsc --noEmit && npm test && VITE_STATIC=1 npx vite build`
Expected: tsc clean, tests pass, build ok.

- [ ] **Step 3: Commit**

```bash
git add web/src/style.css
git commit -m "style: remove area, place-chip, and ai-tag rules"
```

---

### Task 8: Full regression + plan record

**Files:**
- Modify: `docs/superpowers/plans/2026-09-22-darmstadt-refinement.md` (this file — mark checkboxes)

- [ ] **Step 1: Grep-clean check**

Run from the repo root:
```bash
rg -n "placeKeys|placeFiltered|onSelectPlace|onClearPlace|setArea|area-select|map.clearPlace|languageFromStorage|coordKey" web/src
```
Expected: no matches (all removed; `languageFromStorage` may still be legitimately exported by `i18n.mjs` — only `main.tsx`, `i18n.test.mjs`, and `i18n.mjs` itself may reference it in a valid way; check each remaining hit and confirm it's the module export, not a consumer).

- [ ] **Step 2: Full verification**

Run:
```bash
cd /Users/agostontorok/Documents/code/nebenan && .venv/bin/python -m pytest tests -q
cd web && npm test && npx tsc --noEmit
VITE_STATIC=1 npm run build
```
Expected: pytest 99 passed; npm tests **38 passed**, 0 fail; tsc clean; build ok.

Confirm the preview serves both pages:
```bash
curl -s -o /dev/null -w "%{http_code}\n" 127.0.0.1:8765/            # 200 (hub)
curl -s -o /dev/null -w "%{http_code}\n" 127.0.0.1:8765/darmstadt/  # 200 (app)
```

- [ ] **Step 3: Manual visual check (user)**

At `http://127.0.0.1:8765/` (hub) and `http://127.0.0.1:8765/darmstadt/` (app), confirm:
1. Zooming/panning the map narrows and widens the list; cluster clicks drill in; Reset/"All" re-fit the map and show everything.
2. Unmapped events remain listed.
3. No AI badge on list rows; detail panel still shows "This event was extracted…" for `ai_extracted` events.
4. Filter bar: no area select; the map toggle is the rightmost control.
5. Language starts German on a `de` browser, English otherwise.
6. Simple Analytics script tag present in page source.

- [ ] **Step 4: Record outcomes + commit**

Mark every checkbox `- [x]` in this plan after each task completes (the executor does this per-task as it goes). At the end, commit **only this plan file** with explicit paths (never `git add -A` — the tracked sqlite DB under `data/` and the gitignored `web/public/` must not be staged):

```bash
git add docs/superpowers/plans/2026-09-22-darmstadt-refinement.md
git commit -m "docs: complete darmstadt refinement implementation record"
```