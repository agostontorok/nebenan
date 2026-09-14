# First local implementation — verification

The application starts with `./run.sh` at **http://127.0.0.1:8765**. The startup script installed the pinned Python dependencies, built the frontend, and started the localhost server successfully. Data survived a server restart and a second full import without duplicate source references.

## Real collection

The expanded live run finished on **14 September 2026 at 14:13 Europe/Berlin**:

- 692 collected occurrences; 378 published and 313 awaiting review. The increase includes the neighbouring municipal calendars and conservative review of records without clear area evidence.
- Published occurrences from the live run include 10 Griesheim and 57 Weiterstadt records; both municipalities now receive map coordinates, with an approximate municipality-centre marker when no exact venue address is available. A four-day “Grewweheiser Kerb” occurrence retains its 2–5 October end range.
- Eleven enabled collectors and 72 directory entries are visible: the original 69-source research registry plus Griesheim, Weiterstadt and the Spielmobil manual source.
- No test events exist in the real database. Submission/approval browser checks used a separate disposable copy.
- Next update due: **21 September 2026 at 14:13 Europe/Berlin**, while the app is running. The controlled-clock tests cover overdue catch-up and persisted scheduling.

Exact source horizons and errors are in [the verification JSON](2026-09-14-implementation-verification.json). Feed horizons differ; the 90-day extraction window does not imply complete 90-day coverage.

## Automated and browser checks

- Backend: **45 tests passed**. Coverage includes recurrence exceptions and moved instances, DST, standalone rescheduling, source identity and provenance, persistent conflicts and review signatures, stale coordinate invalidation, free-admission changes, failed-fetch preservation, nonoverlap, persisted due times, API review/publication, partial edits, neighbouring municipality parsing, multi-day ranges, event-image metadata/attachment priority and URL safety, private-address rejection, redirected requests, and decompressed response limits.
- Frontend: **19 tests passed**, including Berlin date filtering, multi-day overlap, exclusive end dates, changed-only edits, map fit-once behavior, bilingual copy, searchable Admin event list, and safe image URL handling. Date-edit tests also passed with `TZ=America/Los_Angeles`.
- TypeScript and Vite production build passed. Startup shell syntax passed. A third-party Starlette test-client deprecation warning does not affect test results.
- Independent code review accepted the implementation for the local first batch after the reported update/approval/location issues were corrected.
- Isolated browser checks used a temporary empty profile, with desktop at 1440 px and mobile at 390 px. Map tiles and attribution loaded, mobile list/map switching resized correctly, no horizontal overflow was detected, and no JavaScript errors occurred.
- Actual submission and approval forms worked against the disposable database. A 19:00 Berlin entry remained 19:00 Berlin with the browser configured for Los Angeles. The outgoing edit included only changed fields and the publication decision.
- A disposable browser check confirmed English is the default, EN/DE switching persists in the page, and the Admin view lists 100 searchable published events with edit actions. Map refreshes now preserve a user viewport after the initial fit. Each event detail can also generate a local `.ics` invite with one or more attendee addresses, while available source images render as lazy thumbnails/details with a broken-image fallback.
- Search for Yoga produced three cards and three map markers in the tested week. An unmatched query produced an empty state and zero cards. Source errors and last/next update times appeared in the interface.
- Manual collection through the API returned HTTP 202; a simultaneous second update returned HTTP 409.

## Review-driven corrections

Standalone source identifiers remain stable on rescheduling. Each recurring occurrence has its own identity. Per-source snapshots retain conflicting facts; review approval applies to the source facts actually reviewed and is reopened when relevant validation changes. Human edits no longer freeze untouched source dates or cancellation state. Changed venues invalidate old coordinates. Conflicting title/description addresses go to review instead of receiving an invented pin. Topic matching respects word boundaries; free admission requires explicit event-price evidence.

## Remaining scope limits

Social scraping, broad web search, and OCR are unconfigured. Source links, bounded outgoing-link discovery, manual submissions, and poster reference storage work. Most event sizes are unknown until reviewed with evidence. Additional researched sources need adapters; citywide, family, sports, institutional, and social-only coverage remains incomplete. The app is local and has no production authentication or deployment setup.

## Previews

- [Desktop](../screenshots/desktop.png)
- [Mobile](../screenshots/mobile.png)
- [Mobile map](../screenshots/mobile-map.png)
