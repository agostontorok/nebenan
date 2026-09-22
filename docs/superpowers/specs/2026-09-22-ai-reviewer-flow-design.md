# AI Reviewer Flow — Design

- **Date:** 2026-09-22
- **Status:** Approved (design review, 2026-09-23)
- **Scope:** One implementation plan. A local-only editorial tool to review and fix AI-extracted events, with batch-fix propagation: correcting a field on one event also fixes every other event that shares the identical old value.

## Context

AI extraction (`app/llm_extract.py` via `collect.parse_html_llm`, and `chat_ingest.py`) currently publishes events directly with `ai_extracted: true`. The visible site is the reader-facing surface; the reviewer is the operator. This flow gives the operator a queue to check and correct those published AI events, and — the core requirement — propagates a correction to *every other event in the same source that carries the same wrong value*, after explicit confirmation.

Constraints agreed with the user:

- **Cleanup pass, no pipeline change.** AI events keep auto-publishing; this flow reviews what is already live.
- **Local-only.** The UI and its backend endpoint exist only on the local dev server (`EDITOR && !STATIC`). Nothing new ships to GitHub Pages.
- **Queue with reviewed status.** Source-grouped queue; each event marked reviewed once handled; unreviewed reappear next time.
- **Confirm after each save.** Batch fixes are proposed, never silent.
- **Same review set.** Propagation matches only other AI events from the same source group.
- **Propagation fields:** `venue`, `address`, `title`, `start`, `end`. Description/price/topics/scale never propagate.
- **Hide action.** The reviewer can unpublish (set `status=rejected`) a clearly wrong AI event.

## Changes

### 1. Backend: review-queue endpoint and reviewed marker

**Reviewed-state storage.** A private override `_ai_reviewed_at` (ISO timestamp) is stored on the event, following the existing pattern of `_source_review_signature` (`app/db.py`). `db._event` and the static export already drop every `_`-prefixed override key, so the marker never reaches `data.json` or the visible site.

- `app/main.py` `EventInput` gains `ai_reviewed_at: str | None = None`.
- `edit()` in `app/main.py` maps it to the private override before validation:
  `if "ai_reviewed_at" in changes: changes["_ai_reviewed_at"] = changes.pop("ai_reviewed_at") or None`
  (`validate_publication` ignores the extra key; `db.edit_event` merges it into overrides).

**List endpoint.** `GET /api/review/ai` returns published `ai_extracted` events including their reviewed marker, so the queue can be built and the client is never shown private `_`-prefixed keys. Only reachable on the local backend (TrustedHost localhost; the backend is not deployed).

- `app/db.py`: add `ai_events()` — all events with `status == 'published'` and `ai_extracted` true, each carrying `ai_reviewed_at` read from its `overrides['_ai_reviewed_at']` plus the ordinary effective data and provenance (same shape as `db.events`).
- `app/main.py`: `@app.get('/api/review/ai')` → `{'events': db.ai_events()}`.

### 2. Frontend: AI tab (EDITOR mode only)

- New nav button **AI** in `web/src/main.tsx`, rendered only when `EDITOR && !STATIC` (next to Review/Admin, ~`main.tsx:1005`).
- Tab body rendered when `!STATIC && tab === "ai"`. Shows `GET /api/review/ai` events grouped by source (`event.provenance[0].source_id`, labelled by `provenance[0].name`); groups ordered by name, events in each group by start ascending, **unreviewed first**.
- Each toggleable group header shows source name and a count ("3 of 12 reviewed"); each row is a `review-card` (title, date · venue, a "reviewed"/"needs review" chip driven by `ai_reviewed_at`).
- Data loads when the tab opens and after every mutation via a `loadAi()` that hits `/api/review/ai`; the queue's parent list is kept in `aiEvents` state.

### 3. Queue review modal

- Selecting a row opens a wrapper around the existing `EventForm` modal (reuse `Modal` + `EventForm` at `main.tsx:1934-1946`, keep `event`, `language`, `onDone`).
- The wrapper adds a small header: source name, position in queue, the AI badge/source snapshot line, and queue controls **← prev / skip / next →**, **Mark reviewed**, and **Hide from public**.
- `EventForm` gains one optional prop `onSaved?: (patch) => void | Promise<void>` invoked after a successful PATCH, before `onDone()`. The wrapper uses it to run propagation (below) and then advance to the next unreviewed item; `onDone` closes nothing — the wrapper manages its own modal state.

**Actions**

- **Save / approve** — existing form buttons; PATCH already sends `{...patch}`; the wrapper marks the event reviewed (adds `ai_reviewed_at`).
- **Mark reviewed** — PATCH `{ai_reviewed_at: now}` without other field changes.
- **Hide from public** — PATCH `{status: "rejected", review_reason: "AI review: hidden", ai_reviewed_at: now}`; the event disappears from `/api/events` (published-only) and from the live site after the next push.
- **Skip** — advance without persisting anything.

Reviewed events stay listable (chip) and reopenable; there is no "mark unreviewed" action in v1.

### 4. Batch-fix propagation (core)

Pure module `web/src/ai-review.mjs` exporting:

- `sourceGroup(event)` → group key (label + members) for the parent list.
- `propagationCandidates({ events, original, patch })` → `{ field, oldValue, newValue, matches: [{id, title}] }[]`. Algorithm:
  - `changed = keys(patch) ∩ {venue, address, title, start, end}`
  - for each field, `oldValue = original[field]`; skip if `oldValue` is empty/null or `newValue` equals it (should not happen — patch only stores deltas)
  - **start/end** compared and stored through the existing `berlinInput` normalizer; **venue/address/title** by exact string equality
  - `matches = events.filter(o => o.id !== original.id && normalized(o[field]) === normalized(oldValue))` — same source by construction (the wrapper passes only the current source group), exact-match only
- Candidates are recomputed at confirm time (the saved event is excluded; already-changed events no longer match).

Location edits already clear coordinates: `db.edit_event` sets `lat`/`lon`/`coordinate_evidence` to null whenever `venue`/`address` change (existing behavior for single-event edits). A batch venue/address fix therefore also clears the affected events' pins; re-geocoding happens on the next collection run (cached address lookups). Noted here as intended — a corrected venue should relocate the pin.

In the wrapper's `onSaved`:

1. Reload the source group (`/api/review/ai`) after the edited event's save so propagation never matches stale values, then build `propagationCandidates` from the fresh group.
2. If none, do nothing extra.
3. Otherwise show a confirm listing, per changed field: *"6 other events share venue ›Stadthalle‹ — set it to ›Stadthalle Darmstadt‹?"* with the affected titles. On confirm, PATCH each match with only that field (`{venue: newValue}` etc., no status change); stop on first failure and report. On decline, only the edited event is changed.

No atomic batch endpoint: N sequential PATCHes, each revalidated server-side, same-origin under the existing `local_guard`.

### 5. i18n

Add de/en keys (in `web/src/i18n.mjs`) and the new leaders to the required-key list in `web/src/i18n.test.mjs`:

- `ai.nav`, `ai.eyebrow`, `ai.title`, `ai.intro`, `ai.empty`, `ai.emptyCopy`
- `ai.reviewed`, `ai.needsReview`, `ai.countReview` ("3 of 12 reviewed"), `ai.auditLine`
- `ai.prev`, `ai.next`, `ai.skip`, `ai.markReviewed`, `ai.hide`, `ai.hideConfirm`
- `ai.propagationTitle`, `ai.propagationCopy`, `ai.propagationConfirm`, `ai.propagationNone`

## Local-only guarantee

- The AI tab and modal render only under `EDITOR && !STATIC`; the static build (`VITE_STATIC=1`) never includes them.
- `GET /api/review/ai` lives on the local FastAPI backend only (never deployed; `web/dist` + `web/public/<city>/data.json` are what Pages serves).
- The reviewed marker is a `_`-prefixed override and is stripped from effective data by `db._event` and by the static export — it never appears in public payloads.
- Public readers see only the corrected field values after the next push.

## Non-goals

- No change to the collection pipeline (AI events still auto-publish).
- No atomic batch endpoint, no undo/redo, no "mark unreviewed", no review of manually-submitted events through this flow.
- No new reviewer UI for non-AI events; the existing Review tab is untouched.
- No mobile/non-editor access to the tool.

## Testing

- **Backend (pytest, `tests`):**
  - `GET /api/review/ai` returns only published `ai_extracted` events, grouped client-side data shape intact, `ai_reviewed_at` null for untouched events.
  - `PATCH {ai_reviewed_at: ...}` stores `_ai_reviewed_at` as a private override: the effective event (`GET /api/events` / export) carries no `ai_reviewed_at` or `_ai_reviewed_at` key.
  - `PATCH {status: "rejected", review_reason, ai_reviewed_at}` removes the event from `GET /api/events` and records the marker.
  - Existing suites keep passing.

- **Frontend (npm, `web/src`):**
  - New `ai-review.test.mjs`: `propagationCandidates` — matches only in the given (same-source) set and only on the propagation fields; exact match; excludes the edited event; `berlinInput` normalizes start/end; no candidates for description/price/topics changes; empty old values skipped.
  - `i18n.test.mjs`: new keys added to the required-key list.

- **Gates:** `cd web && npm test` (39 + new), `npx tsc --noEmit`, `VITE_STATIC=1 npx vite build` (public bundle unchanged in behavior), `.venv/bin/python -m pytest tests -q` (99 + new).

## Reference

- `app/db.py`: `events()`/`_event`/provenance shape (`~95-136`), private-override pattern (`_source_review_signature`, `~215-233`), `edit_event` (`~241-265`).
- `app/main.py`: `EventInput` extra-forbid model (`~20-60`), `edit()` (`~188-204`).
- `web/src/main.tsx`: tab state (`~693`), nav (`~975-1011`), review/admin tabs (`~1633-1737`), editing modal + EventForm wiring (`~1934-1946`), `mutate`/`refresh` (`~886`).
- `web/src/event-patch.mjs`: `eventPatch` + `berlinInput` (reused for start/end normalization).
- `web/src/i18n.mjs` + `i18n.test.mjs`: key lists.