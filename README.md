# Darmstadt Local

A local event portal for Darmstadt: real source calendars, a synchronized map and list, a source directory, and a local review desk. The application and SQLite database live on your computer.

## Run

Requires Python 3.11+, Node 20.19+ (or 22.12+), npm, and `/usr/bin/curl`.

```sh
./run.sh
```

Open **http://127.0.0.1:8765**. The first start installs dependencies and builds the website. Click **Update / Jetzt aktualisieren** to run the first collection. Subsequent updates run every seven days while the server is running. An overdue update runs once after restart. Closing the process or sleeping the computer pauses collection. Set `PORT=8766 ./run.sh` to use another port.

No cloud credentials are needed. Fetching source websites, geocoding addresses, and loading map tiles require internet access. The application binds to localhost; it is not ready for public hosting or shared administration.

## What works

- Eleven implemented collectors: the original nine plus the Griesheim and Weiterstadt municipal calendars. The **72-source directory** includes the original research set, the Spielmobil manual source and those two municipal additions. Source errors are shown individually.
- Calendar recurrence expansion over the next 90 days, including date exceptions, moved occurrences, Berlin daylight-saving time, and multi-day ranges such as festivals. The upstream feed may expose a much shorter horizon; the source record stores its observed first and last dates.
- Event images are selected from JSON-LD, Open Graph/Twitter metadata, or a scoped event image when the source exposes one. They remain hosted by the original publisher and are hidden if the URL is unsafe or the image fails to load.
- Text, date, topic, size, and free-admission filters over the same event set for both map and list. Unknown size/price/location stays unknown. Topics use transparent keyword classification; review can correct them. Size requires source evidence or an administrator's reviewed estimate.
- The discover search also uses a local multilingual embedding model in a browser worker. A query such as `fitness` can include related events such as `Zumba`; exact matches remain included, and the interface falls back to exact search if the model cannot load. The model is fetched on first semantic search and then cached by the browser; event vectors are cached locally in IndexedDB. Admin search remains lexical.
- English is the default interface language; the header switch provides German and remembers the choice locally. The map fits the first available result set once, then preserves a user's pan/zoom while the ten-second data refresh updates markers.
- Each event detail can create a local `.ics` calendar invite. Enter one or more attendee email addresses, download the invite, then send or import it from your calendar application.
- SQLite storage, source provenance, duplicate handling, persistent manual corrections, and a review queue. Complete records with an explicit Darmstadt-area location (Darmstadt, Griesheim or Weiterstadt) are published; uncertain or regional records need review. The local Admin view can search published events and edit tags, dates, locations, size, admission and cancellation state. A failed fetch preserves existing records and does not imply cancellation.
- Manual URL/text/event submissions and optional PNG/JPEG posters. Posters are stored as reference material; no OCR is configured. Corrections and publication decisions are made locally.
- Bounded discovery of relevant outgoing links from enabled source websites. Suggestions enter a candidate queue; accepting one marks it for integration, it does not create an unverified collector.
- Source-provided coordinates plus cached Nominatim lookup of explicit street addresses (up to 20 new lookups per update, serial, 1.1 seconds apart). Griesheim and Weiterstadt entries without an exact venue use an explicitly labelled approximate municipality-centre pin; other ambiguous or missing locations have no pin until review supplies coordinates.

## Coverage limits

Instagram/Facebook automatic collection, broad search-engine discovery, and poster OCR are **not configured**. Social links and manual intake work; the Das Rotzfreche Spielmobil is intentionally a manual source because its route is published as a schedule/posters rather than a stable feed. Event images are not downloaded or re-hosted, and the collector only inspects the already fetched source page. The source directory distinguishes researched sources from implemented adapters; this first version does not collect all 72 sources or claim exhaustive city coverage. Some source feeds cover only a few days. Empty upcoming results can be valid; fetch and parser failures are separate states.

Semantic search is computed in the browser with the open-source Transformers.js runtime. The first query may take longer while model assets are downloaded; later queries reuse the browser cache. Automated tests intentionally use a fake worker and never download model weights.

Most events initially have **unknown size** because the sources do not state attendance. Set size in review with evidence; the small-gatherings filter becomes useful as those classifications are reviewed. Regional calendars and events without clear Darmstadt venue evidence remain in review. Source disappearance alone does not remove an event. Confirmed source cancellation and manual cancellation remain visible.

The mapping service follows the [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/). OpenStreetMap attribution remains visible. Calendar handling uses the documented [recurring-ical-events occurrence API](https://recurring-ical-events.readthedocs.io/en/v3.8.0/reference/api.html).

## Deploying

The public site is static and read-only. `scripts/build-static.sh` is the single static build: it exports the committed `data/events.sqlite` with `app/export_static.py` and builds `web/` with `VITE_STATIC=1`. GitHub Pages runs that script from `.github/workflows/pages.yml` on every push to `main`, and `vercel.json` builds Vercel from the same script into the same `web/dist` output.

`VITE_STATIC=1` makes the build read-only: the frontend fetches `./data.json` instead of calling the API, and Admin, Review, submissions and editing are absent. Those stay in the local `./run.sh` server, which never sets `VITE_STATIC`. Visitors submit events through the GitHub issue templates.

To refresh the live data, run a collection locally, then use **Publish & push to GitHub** in the editor view. It checkpoints the SQLite write-ahead log before committing, and only `data/events.sqlite` is tracked, so the committed database is self-contained. Committing that database without the checkpoint deploys the older state, because the write-ahead log is ignored and never reaches the build; the site keeps the older data until the next publish.

## Storage and development

`data/events.sqlite` holds events, source states, provenance, review edits, geocoding cache, and schedule. The database is tracked by Git; `data/posters/` holds submitted posters and stays ignored. Back up `data/` with the server stopped. To use a separate database, set `DARMSTADT_DB=/absolute/path/events.sqlite`.

```sh
.venv/bin/python -m pytest -q
cd web
npm test
npm run build
```

For frontend development, run the Python API on port 8765, then `cd web && npm run dev` (Vite proxies `/api` to the local API). Keep production operation on the single-origin `run.sh` server. Fetches accept only public HTTP(S) destinations, revalidate every redirect, pin DNS answers, verify TLS, and impose size/time limits. Local changes reject foreign origins.

Architecture: `app/collect.py` extracts and validates; `app/db.py` persists data and overrides; `app/network.py` bounds public requests; `app/main.py` exposes the API and scheduler; `web/` renders the interface. The researched inventory is `docs/research/darmstadt-sources.json`.

### Editor mode and GitHub issues

Run `MODE=editor ./run.sh` to start the local editorial desk with only the Review and Admin views; the Admin view includes a **Publish & push** control that mints a commit and pushes `data/events.sqlite` to the repo. The database is tracked; its WAL sidecar files and `data/posters/` remain ignored.

Visitors share events by opening the **Share an event** issue template on the GitHub repo (issues labeled `submission`). Import those into the local review queue with:

```sh
PYTHONPATH=. .venv/bin/python -m app.import_issues        # dry run
PYTHONPATH=. .venv/bin/python -m app.import_issues --import
```

First-time use on a fresh repo: create the label once with `gh label create imported`.

Each issue becomes a review-queue event with provenance pointing at the issue; a poster dragged into an issue comment is stored as reference material. Imported issues get the `imported` label and a confirmation comment; invalid submissions receive an explanation on the issue.

### Public site on GitHub Pages

The committed database is mirrored online as a read-only site at **https://agostontorok.github.io/nebenan/**. Every push to `main` runs [`.github/workflows/pages.yml`](.github/workflows/pages.yml), which runs the test suite, exports the published review state from `data/events.sqlite` into `web/public/data.json` with `app/export_static.py`, builds `web/` with `VITE_STATIC=1`, and deploys `web/dist`. The editor's **Publish & push** control commits the database to `main`, so the public page redeploys automatically after each publish.

To rebuild manually, run the workflow from the Actions tab (**Run workflow** on *Deploy to GitHub Pages*), or locally:

```sh
PYTHONPATH=. .venv/bin/python -m app.export_static
cd web && VITE_STATIC=1 npm run build
```

The static build loads `./data.json` and needs no backend, so interactions that would call the API — event submissions, source suggestions, review decisions, admin publish — are unavailable on the public site. Sharing still happens via the **Share an event** issue template. Submitted posters stay local (`data/posters/` is gitignored); remote `image_url` images do appear.
