# First local implementation

> **For agentic workers:** Use the subagent-driven-development workflow for the independent interface task and requesting-code-review for the completed app. Steps use checkbox syntax for tracking.

**Goal:** Run a usable Darmstadt event portal on localhost with real collected events, a map, filters, weekly updates, and local review.

**Architecture:** FastAPI serves a React/Vite application and JSON API from one localhost port. SQLite persists events, provenance, review edits, sources, and scheduling. Python calendar adapters use `icalendar` and `recurring-ical-events`; bounded public HTTP requests use system curl with pinned public IPs and redirect validation.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, pytest, React, TypeScript, Vite, Leaflet.

## Global Constraints

- Everything runs locally; internet is needed for collection and map tiles. Bind to 127.0.0.1.
- Real source data only. Never invent event times, attendance, prices, or map pins.
- Scale is independent of topic and defaults to unknown until reviewed.
- Persist information and review decisions across imports and restarts. Failed fetches preserve events.
- Expand explicit recurrence rules with exceptions into distinct occurrences within a 90-day window.
- Apply identical filters to map and list. Unresolved venues remain visible in the list.
- Weekly collection runs only while the app is running; persist due times and catch up once after restart.
- Show the distinction between implemented collectors and the 69 researched sources. Social scraping, OCR, and broad search are not configured.
- Treat remote text as untrusted. Bound fetch size/time/redirects and reject private addresses. Protect local mutation endpoints from cross-origin requests.
- Work only inside this new project directory; the parent Git repository contains unrelated work. Do not commit or change the parent branch.

## Task 1 — data and collection

- [x] Add pinned Python dependencies and failing tests for recurrence/DST/exceptions, deduplication, provenance, preserved review edits, failed fetches, and scheduler catch-up.
- [x] Implement `app/db.py`, `app/collect.py`, `app/network.py`, and configured collectors in `app/sources.py`.
- [x] Start with eight independent calendar publishers (NBH, Eberstadt, Lincoln, Postsiedlung, Jazzinstitut, vielbunt, Transition, FRIZZ) plus Krone JSON-LD. Bound regional results to Darmstadt evidence or review.
- [x] Persist the full researched source directory and bounded outgoing-link candidates. Cache source-provided venue coordinates; provide manual coordinate correction where unresolved.
- [x] Run the meaningful backend tests and live collection; inspect actual upcoming events and provenance.

## Task 2 — local API and interface

- [x] Implement `app/main.py`: events, sources, status, collection, submission, review, and source suggestion endpoints; persistent scheduler and same-origin mutation guard.
- [x] Implement `web/` React interface: polished responsive map/list, text/date/topic/scale/free filters, details, source coverage, collection status, submissions, and review editing.
- [x] Include loading, empty, failure, unknown-location, and cancellation states. All displayed remote text is escaped.
- [x] Verify API validation, queue publication, persistence, and filtered map/list agreement.

## Task 3 — run and verify

- [x] Add `run.sh`, `.gitignore`, and README with local setup, real capabilities, maintenance, and limitations.
- [x] Build the frontend, run backend tests, exercise collection and persistence, and inspect desktop/mobile in a real browser.
- [x] Request independent code review, fix important findings, repeat affected verification, and record evidence.
- [x] Leave the local server running and give the user its URL.

## API contract for the interface

All endpoints are same-origin under `/api`. Event fields: `id,title,start,end,all_day,venue,address,description,image_url:string|null,topics:string[],scale,scale_evidence,price,free:boolean|null,lat:number|null,lon:number|null,status` (published/review/rejected), `cancelled:boolean,review_reason,last_checked,provenance:[{source_id,name,url,checked_at}]`. Dates are ISO strings with offset; render Europe/Berlin. `GET /events` returns `{events:[...]}` (published); `GET /review` returns the same shape (review). Frontend handles filters consistently over fetched events. `GET /status` returns `{running,last_run,next_due,last_result,source_count,active_sources,event_count,review_count,capabilities:{social:false,ocr:false,web_search:false},collection_progress}`. `GET /sources` returns `{sources:[{id,name,url,category,enabled,implemented,method,last_attempt,last_success,error,event_count,linked_social_profiles:[{url}],limitations}],candidates:[{id,url,title,found_on,status}]}`. `POST /collect` returns 202 or 409. `POST /submissions` accepts event fields plus `source_url` and optional `poster` as base64 data URL; title required, missing date/location goes to review. `PATCH /events/{id}` accepts editable event fields and status. `POST /sources/suggest` accepts `{url,title}`; `PATCH /sources/{id}` accepts `{enabled:boolean}` for implemented adapters only. `PATCH /candidates/{id}` accepts `{status:"accepted"|"rejected"}` (accepted means directory candidate for manual integration, not automatic scraping).
