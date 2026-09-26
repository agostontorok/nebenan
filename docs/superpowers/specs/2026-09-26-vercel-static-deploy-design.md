# Vercel Static Deploy — Design

- **Date:** 2026-09-26
- **Status:** Approved (2026-09-26)
- **Scope:** One implementation plan. Adds a Vercel deployment of the existing read-only static site, without changing application behaviour and without removing the GitHub Pages deploy.

## Context

`nahe` is a local-first event portal: a FastAPI backend (`app/`) with a SQLite database that is committed to git, and a Vite/React frontend (`web/`) that is served from the same origin by `app/main.py`. The local server binds to `127.0.0.1` and the README states it "is not ready for public hosting or shared administration".

The repository already contains a complete static-export path, used by `.github/workflows/pages.yml`:

1. `pip install -r requirements.txt`
2. `PYTHONPATH=. python -m app.export_static` → writes `web/public/darmstadt/data.json`
3. `cd web && VITE_STATIC=1 npm run build` → `web/dist`
4. deploy `web/dist`

`VITE_STATIC=1` is the switch that makes the frontend read-only: `web/src/main.tsx:24` sets `STATIC`, `refresh()` fetches `./data.json` instead of `/api/*` (`main.tsx:766`), and every mutating surface (Admin, Review, Submit, Edit, Suggest) is hidden behind `!STATIC`.

The goal is to serve that same static site from Vercel so a custom domain can be attached, for public visitors only. Data refresh follows the existing local flow: a collection runs locally, the editor's "Publish & push" commits `data/events.sqlite`, and the push triggers a rebuild. GitHub Pages stays in place.

## Approaches considered

**A. Vercel builds from the git push (chosen).** `vercel.json` with `framework: null` and a single `buildCommand` running the same three steps as `pages.yml`. Vercel's build environment ships Node, Python, Ruby and Go, so no Builds API, no functions, and no uv involvement.

**B. GitHub Actions builds and deploys to Vercel.** CI runs today's `pages.yml` steps, then `vercel deploy --prebuilt --prod` with a `VERCEL_TOKEN`. Zero new build-environment assumptions, but adds a token secret and a second workflow, and pushes only reach Vercel when CI runs. This is the fallback if A fails.

**C. Serve the FastAPI app as a Vercel function. Rejected.** Vercel functions get a read-only filesystem (`/tmp` only), so SQLite writes for review and submissions break, and the collector scheduler in the `lifespan` hook (`app/main.py:90`) never runs. This is what Vercel attempted when it auto-detected `requirements.txt` and tried to serve `app.main:app` — the failure that started this work.

## Architecture

One canonical build script, two callers. No runtime component, no database access at request time, no environment variables.

```
git push to main
   ├── GitHub Actions (pages.yml)  ──▶ scripts/build-static.sh ──▶ web/dist ──▶ GitHub Pages
   └── Vercel (git integration)     ──▶ scripts/build-static.sh ──▶ web/dist ──▶ Vercel CDN
```

`scripts/build-static.sh` is the single definition of the static build. Both deploy targets call it, so they cannot drift.

## Changes

### 1. `scripts/build-static.sh` (new, `chmod +x`)

Runs from the repository root, mirrors the `pages.yml` step order, fails loudly on any error:

```sh
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Python dependencies for the data export.
if python3 -m pip --version >/dev/null 2>&1; then
  python3 -m pip install -r requirements.txt
elif command -v uv >/dev/null 2>&1; then
  uv pip install --system -r requirements.txt
else
  echo "build-static: need pip or uv to install requirements.txt" >&2
  exit 1
fi

# 2. Export the database to the static JSON the read-only frontend fetches.
PYTHONPATH=. python3 -m app.export_static

# 3. Build the frontend in read-only mode.
cd web
npm ci
VITE_STATIC=1 npm run build
```

Notes:
- `requirements.txt` keeps `pytest`, which is harmless; the script does not run tests. Test gating stays in `pages.yml`, which already runs `python -m pytest -q` before building.
- The `pip`-then-`uv` branch is the mitigation for a build image that ships only one of the two.
- `export_static` writes to `web/public/darmstadt/data.json` by default (`app/export_static.py:6`); Vite copies `public/` to the output root, so the file lands at `web/dist/darmstadt/data.json`, which is what `/darmstadt/` requests.

### 2. `vercel.json` (new)

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "installCommand": "",
  "buildCommand": "bash scripts/build-static.sh",
  "outputDirectory": "web/dist",
  "trailingSlash": true
}
```

Field by field:
- `framework: null` — selects the "Other" preset and is what stops Vercel auto-detecting `requirements.txt` and serving `app.main:app`. This is the fix for the reported failure.
- `installCommand: ""` — skips the install step. There is no root `package.json`; `npm ci` happens inside the build script against `web/`.
- `buildCommand` — the only build step; see above.
- `outputDirectory: "web/dist"` — static output, no functions.
- `trailingSlash: true` — **required, not cosmetic.** See "Routing" below.

### 3. `.vercelignore` (new)

Reduces the upload and keeps uncommitted local state out of the build:

```
.venv/
.git/
.github/
__pycache__/
.pytest_cache/
node_modules/
data/events.sqlite-wal
data/events.sqlite-shm
data/posters/
docs/
tests/
run.sh
```

`data/events.sqlite` itself stays included — the export reads it. The `-wal` and `-shm` files are excluded deliberately: they are 3.9 MB of uncommitted local state, and SQLite recreates them on open.

### 4. `.github/workflows/pages.yml` (modified)

Replace the three inline build steps with the shared script, keeping the existing test gate, Node setup, and Pages upload:

```yaml
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Run tests
        run: python -m pytest -q

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Build static site
        run: bash scripts/build-static.sh

      - uses: actions/configure-pages@v5
```

The four existing steps — `Install Python dependencies`, `Export static review state`, `Install frontend dependencies`, `Build static site` — collapse into one, because the script now performs the install, the export, and `npm ci` + `VITE_STATIC=1 npm run build`. `actions/setup-python` and `actions/setup-node` stay, because the test gate above still needs Python and the script's `npm ci` still needs Node 20; both were already pinned by the existing workflow.

Behaviour of the Pages deploy is unchanged: same artifact, same commands, same order.

### 5. `README.md` (modified)

Add a short "Deploying" section covering:
- The Vercel deployment is the public, read-only site. Admin, Review and submissions are local-only.
- Data refreshes on every push; run a collection locally, then use the editor's "Publish & push".
- `events.sqlite` must be committed after a WAL checkpoint. `Database.checkpoint()` (`app/db.py:78`) runs `PRAGMA wal_checkpoint(TRUNCATE)` and is called on the push path, so the committed file is self-contained. Committing without a checkpoint silently deploys older data.
- GitHub Pages remains the second deploy target, built from the same script.

## Routing

`vite.config.ts` sets `base: "./"`, so the app fetches `./data.json` relative to the current URL. Vercel's default (`trailingSlash: undefined`) serves both `/darmstadt` and `/darmstadt/` with a 200 and no redirect. At `/darmstadt` the browser resolves `./data.json` to `/data.json`, which does not exist, and the page renders empty.

`trailingSlash: true` makes Vercel answer `/darmstadt` with a 308 to `/darmstadt/`. Paths with a file extension are never redirected, so `/assets/*.js` and `/darmstadt/data.json` are unaffected. It also avoids the duplicate-content indexing the Vercel docs warn about for the undefined case.

`web/index.html:110` already links `darmstadt/` with the trailing slash, so the hub is unaffected, and `/` serves the hub's `index.html` unchanged.

## Data flow

1. A collection runs locally via `./run.sh` (or `MODE=editor ./run.sh`) and updates `data/events.sqlite`.
2. The editor's "Publish & push" checkpoints the WAL and commits the database.
3. The push triggers both deploys. Each checks out the commit, including the new `events.sqlite`.
4. `app.export_static` reads the database and writes events, sources, candidates, review rows and status into `data.json`.
5. Vite bakes `data.json` into `web/dist`. The deployed site is immutable until the next push.

## Error handling

- `set -euo pipefail` in the script: any failing step fails the build and blocks the deploy rather than shipping a half-built site.
- Missing `pip` and `uv` both: the script exits 1 with an explicit message.
- `export_static` failing on a corrupt or locked database fails the build. The deploy then keeps serving the previous successful build.
- No custom headers, rewrites or middleware. The site is static and the previous deployment stays live if a build fails.

## Testing

- Run `bash scripts/build-static.sh` locally; it must produce `web/dist/darmstadt/data.json` and `web/dist/index.html`.
- Confirm the frontend build still contains no Admin/Review entry points, i.e. `VITE_STATIC=1` is in effect.
- Push and confirm the Pages workflow is green and the artifact is served.
- Deploy to Vercel and confirm the build is green, `/` loads the hub, `/darmstadt` redirects to `/darmstadt/`, `/darmstadt/data.json` returns JSON, the map and filters work, no `/api/*` request is made, and no Admin or Review tab is present.

## Risks

1. **Build image lacks `pip`.** Mitigated by the `uv` fallback. If neither exists, fall back to approach B (GitHub Actions builds, deploys prebuilt) without changing anything already working.
2. **Python version drift.** Pages pins 3.12; Vercel's image default may differ. `requirements.txt` pins exact versions and the app targets 3.11+, so resolution should succeed. If it does not, add a `.python-version`.
3. **Stale data.** Only if `events.sqlite` is committed without a checkpoint; documented in the README. Not recoverable after the fact, since uncommitted WAL content is never pushed.
4. **Upload size.** `.venv/` and `web/node_modules/` are large; `.vercelignore` keeps them out. `data/events.sqlite` is 5.4 MB and is intentionally included.

## Out of scope

- The GitHub Pages deploy is not removed.
- No custom domain configuration (a dashboard step after the deploy is verified).
- No server-side API, no write path, no submissions on the deployed site. The "Share an event" modal is already hidden by `!STATIC` (`web/src/main.tsx:1918`); visitors use the GitHub issue template, as today.
- No change to `app/`, `web/src/`, or the local `run.sh` flow.
