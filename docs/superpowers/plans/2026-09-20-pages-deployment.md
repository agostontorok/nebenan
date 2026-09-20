# Plan: GitHub Pages deployment for the public site

Date: 2026-09-20
Status: Draft for approval
Depends on: #1-#11 of `2026-09-19-issue-intake-and-editor.md` (main now at `63c9354`, pushed as `6814661..63c9354`).

## Goal

Deploy the public site to GitHub Pages. Because Pages cannot run the FastAPI
backend, every push to `main` runs a GitHub Action that:

1. reads the committed `data/events.sqlite`,
2. exports the published review state to a static `data.json`,
3. builds `web/dist` in a new **static-data mode** (`VITE_STATIC=1`),
4. deploys `web/dist` to Pages.

Each editor "Publish & push" (`POST /api/push`) commits `data/events.sqlite`
to `main`, which auto-triggers the workflow and redeploys the page. This makes
the Pages site a live mirror of the review queue.

## Non-goals / accepted limits

- The review/edit/submit/admin mutations are unavailable on Pages (no backend).
  The static build therefore hides share button, review actions, source
  suggest, and admin publish controls; read-only views (Discover, Sources,
  Review list) render from the export.
- Poster binaries (`data/posters/`) stay gitignored, so events with
  `poster_url` render without that image on Pages (currently 0 events have
  one). Remote `image_url` events render normally.
- The DB stays the source of truth and is committed (already the design).

## Plan

### Task A: Commit the current database (seed)

- [ ] **Step 1**: Fold WAL into the main file so the snapshot is consistent:
  `PYTHONPATH=. .venv/bin/python -c "from app.db import Database; Database().checkpoint()"`.
  If busy, fallback: `sqlite3 data/events.sqlite "VACUUM INTO '/tmp/seed.sqlite'"`
  then replace `data/events.sqlite`.
- [ ] **Step 2**: Confirm `data/events.sqlite-shm/-wal` still ignored;
  `git add -f data/events.sqlite`.
- [ ] **Step 3**: Commit `chore: track current review state`.

### Task B: Static export script `app/export_static.py`

- [ ] **Step 1**: Module `app/export_static.py` with `main(argv)`:
  - reads the DB like the API does (`Database()`),
  - builds one JSON object that mirrors the four bootstrap payloads in shape:
    `{events: db.events('published'), review: db.events('review'),
      sources: db.sources(), candidates: db.candidates(),
      status: <same shape as /api/status>}`,
  - `status` fields: `running:false, last_run, next_due, last_result,
    source_count, active_sources, event_count, review_count,
    collection_progress` exactly as `app/main.py` `/api/status` builds them,
  - writes pretty JSON to `web/public/data.json` (creating `web/public/`).
- [ ] **Step 2**: Unit tests (`tests/test_export_static.py`): tmp DB fixture
  (reuse the db fixture pattern from existing tests); assert the payload
  equals what the db methods return, only published+review sets included, and
  events carry `id` + `provenance`.
- [ ] **Step 3**: Commit `feat: export static review state for Pages`.

### Task C: SPA static-data mode (`VITE_STATIC=1`)

- [ ] **Step 1**: `web/src/main.tsx`: `const STATIC = import.meta.env.VITE_STATIC === "1";`
- [ ] **Step 2**: `refresh()`: in static mode, load `./data.json` once on mount
  (no 10 s interval; no `/api` calls) and populate events/sources/status/
  review from it, in the same state shapes.
- [ ] **Step 3**: `web/vite.config.ts`: set `base: "./"` so assets and
  `./data.json` resolve under any Pages subpath. Confirm the existing
  `npm run build` (public) and `VITE_EDITOR=1` (editor) builds still work —
  relative base serves fine at `/` via run.sh.
- [ ] **Step 4**: When `STATIC`, hide: Share button, source-suggest and
  submission affordances, review action buttons, and the admin publish/push
  control. Read-only Review and Admin lists stay visible. `VITE_STATIC` is
  independent of `VITE_EDITOR`; the Pages site is public static.
  Note: esbuild folds the load branch so the static runtime calls only the
  `./data.json` loader (verified: no poll interval, no `/api` network call);
  the live-loader definition may remain in the bundle as unreachable code
  ("dead, not elided") — accepted. `setInterval(fn,1e4)` present only in
  non-static builds.
- [ ] **Step 5**: Type-check + build all three variants: default, `VITE_EDITOR=1`,
  `VITE_STATIC=1` (tsc via `npm run build`). Run `cd web && npm test`.
- [ ] **Step 6**: Commit `feat: static-data build for GitHub Pages`.

### Task D: GitHub Actions workflow `.github/workflows/pages.yml`

- [ ] **Step 1**: Workflow:
  - on: `push: branches: [main]`; `workflow_dispatch`.
  - `concurrency: {group: pages, cancel-in-progress: false}`.
  - permissions: `contents: read; pages: write; id-token: write`.
  - build job (ubuntu-latest): checkout, setup-python (3.12),
    `pip install -r requirements.txt`, `python -m pytest -q`,
    `python -m app.export_static`, setup-node (20), `npm ci`,
    `VITE_STATIC=1 npm run build`, `actions/configure-pages`,
    `actions/upload-pages-artifact` (path: `web/dist`).
  - deploy job: needs build; `actions/deploy-pages`.
- [ ] **Step 2**: Enable Pages with Actions source via API if not set:
  `gh api -X POST repos/agostontorok/nebenan/pages -f build_type=workflow}`.
- [ ] **Step 3**: Commit `ci: deploy published review state to Pages`.

### Task E: README documentation

- [ ] **Step 1**: Document: push to main redeploys the Pages site; editor
  Publish & push triggers it by committing the DB; `VITE_STATIC` &
  `app.export_static`; the site is a read-only mirror (sharing via issue
  template). Keep styles consistent with `README.md`.
- [ ] **Step 2**: Commit `docs: document the Pages deployment`.

### Task F: End-to-end verification

- [ ] **Step 1**: Locally: `app.export_static` → `VITE_STATIC=1 npm run build`;
  serve `web/dist` over `python -m http.server`; headless-DOM check that
  events render and no `/api` call is made.
- [ ] **Step 2**: Push `main`; `gh run watch` the workflow to green; confirm a
  Pages deployment is created (`gh api repos/.../deployments` /
  `repos/.../pages`), fetch `https://agostontorok.github.io/nebenan/` and
  `./data.json`, headless-DOM check that the page lists events.
- [ ] **Step 3**: Confirm the public (`npm run build`) and editor builds did
  not regress (existing local suites stay green).

## Notes

- `web/dist` and the new `web/public/data.json` build artifacts: `data.json`
  is produced by the exporter at build time, not committed.
- `app/export_static` imports `app.db` (which imports `app.sources`), so the
  workflow installs `requirements.txt` before running it.
- No secrets: the workflow is public-repo safe; the DB is committed by design.