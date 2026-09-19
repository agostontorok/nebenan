# Issue Intake and Editor Workflow

Date: 2026-09-19

## Context

Darmstadt Local currently runs as a single-origin FastAPI + SQLite app (`./run.sh`)
that serves the public map/list UI, a local review queue, and an admin workspace.
Reads and writes all go through the same `/api` surface.

We want to (a) let visitors share events as GitHub issues with zero new
infrastructure, and (b) run the review/admin surface as a local-only editor mode
that pushes a reviewed, committed SQLite DB back to GitHub. A later, separate
spec will cover the static GitHub Pages build and weekly action that consumes
that committed DB; that work is explicitly out of scope here and flagged as a
dependency.

## Decisions

- **Approach: Git-native, single repo.** Everything lives in `agostontorok/nebenan`.
  The repo becomes both the source of truth and (in the future) the delivered site.
- Sharing is done via a GitHub issue-form template, not a worker/serverless function
  (no token storage, no external infra).
- Issues reach the local review queue through a CLI import tool that reuses the
  existing submission validation path.
- The SQLite DB is un-ignored and committed to the repo.
- The editor is a mode flag in the existing app, not a separate codebase.
- Pushing is a button in the editor UI that stages only the DB file.

## Architecture

### 1. Intake: "Share an event" → GitHub issue

`.github/ISSUE_TEMPLATE/event-share.yml`, using the GitHub issue-form schema
(https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms).
Fields mirror `EventInput` (`app/main.py:30`): title, start, end, venue, address,
description, price/free, and a note on attendance. The form sets `labels:
["submission"]` via the form's `labels` key.

- The public "Share an event" control deep-links to
  `https://github.com/{owner}/{repo}/issues/new?template=event-share`. In the
  local editor build that control does not appear; the real modal form
  (`web/src/main.tsx` `EventForm`, ~line 370) remains and still POSTs to
  `/api/submissions`.
- Issue forms do not support file uploads, so the template instructs:
  *"After creating the issue, drag & drop the poster image into a comment."*
  The import tool picks it up from there.

### 2. CLI import tool (`app/import_issues.py`)

Pulls open submission issues into the local review queue:

- Runs `gh issue list --label submission --state open --json <fields>` using the
  user's existing `gh`/git auth. No token is stored in the app.
- Parses the form-schema body (issues render as `### field` markdown sections)
  back into `EventInput` fields.
- Reuses the exact validate-and-insert path from `app/main.py:159`
  (`base_event` → `validate_publication` → `db.upsert_event(..., 'manual', ...)`
  with `status='review'`), setting provenance / `source_url` to note `issue #N`.
- If a poster image is attached as a comment, downloads it into `data/posters/`
  as reference material (same behavior as the current endpoint).
- After import: adds label `imported` and a short comment on the issue so
  re-runs skip it. On validation failure: comments the error on the issue and
  leaves it open.
- `--dry-run` prints what would import; `--import` performs it.

### 3. Local editor mode

Single app, two faces, controlled by an env flag `DARMSTADT_MODE=editor`
(runnable as `MODE=editor ./run.sh` or `DARMSTADT_MODE=editor ./run.sh`).

- Backend: all endpoints remain as-is; the editor runs the same localhost app.
- Frontend: a build-time variant (`vite build` with an editor env flag /
  `import.meta.env.VITE_EDITOR`) that renders only the Review and Admin tabs and
  hides Discover/Map/Sources/Share. The tab filter is the single spot in
  `web/src/main.tsx` (~line 873). Reuses existing `review-card`, `EventForm`,
  and admin components.
- `run.sh` passes the flag into both the Python app and the Vite build.

No new directory and no duplicated frontend.

### 4. Publish & push button

In the editor Admin workspace, a "Publish & push" control that:

1. Calls `POST /api/push` (new local endpoint).
2. The endpoint checkpoints the SQLite WAL for consistency, then runs
   `git add data/events.sqlite` (only that file, never other uncommitted
   changes), `git commit -m "events: publish review state"`, and
   `git push origin <current-branch>`.
3. Returns a status string consumable by the existing toast pattern.
4. Guards:
   - Only `data/events.sqlite` is ever staged; unrelated WIP (e.g. edits to
     `web/src/main.tsx`) is never staged.
   - If the DB has no changes since the last commit, report "nothing to publish"
     instead of a no-op commit.
   - Posters under `data/posters/` stay gitignored and are not committed.

### 5. DB in git, ignores, docs

- `.gitignore`: un-ignore `data/events.sqlite`; keep `data/events.sqlite-shm`
  and `-wal` ignored.
- `README.md`: document the editor mode, the import CLI, and the share-via-issue
  flow.
- Tests: parser unit tests for the issue-form body → `EventInput` mapping; a
  `main.py` test for `/api/push` with a mocked git; keep the existing pytest and
  `npm test` suites green. The editor build is verified via the existing build
  script.

## Data flow

Visitor → issue-form template → submission issue (label `submission`) →
`app/import_issues.py` → local review queue in SQLite → editor mode reviews and
edits → "Publish & push" commits/pushes `data/events.sqlite` → (future) Pages
action builds the static site from the committed DB.

## Out of scope

- Static GitHub Pages build and weekly action consuming the committed DB
  (explicit dependency, to be specced separately).
- Automated issue → publish loop; cloud worker/serverless intake.

## Testing strategy

- `tests/` (pytest): import parser unit tests; `/api/push` with mocked git.
- `web`: `npm test` stays green; editor build verified via `npm run build`.
- Manual: `MODE=editor ./run.sh` shows only Review/Admin; "Publish & push"
  commits/pushes only the DB.