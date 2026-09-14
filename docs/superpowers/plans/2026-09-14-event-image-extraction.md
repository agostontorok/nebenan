# Event Image Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve publicly declared event images from supported event pages and display them safely in the local portal when available.

**Architecture:** Add a pure image-selection helper in the Python collector that prioritizes JSON-LD `Event.image`, Open Graph, Twitter metadata, and relevant page images. Store the validated remote URL on each event; do not download or re-host it. The React list/detail views render the optional URL with a fallback, while source links remain the authority.

**Tech Stack:** Python 3.11+, BeautifulSoup, pytest, React, TypeScript, Vite, Node test runner.

## Global Constraints

- Keep all collection and storage local; remote images remain hosted by the source.
- Accept only validated public `http(s)` image URLs; reject data URLs, JavaScript URLs, localhost, private-network addresses, and obvious favicon/logo assets.
- Preserve current event publication, provenance, map, bilingual, and calendar-invite behavior.
- Keep image extraction bounded to the already fetched event/source HTML; do not add unbounded image crawling or OCR.
- Run focused red-green tests before the full backend/frontend verification suites.

### Task 1: Image extraction helper and parser integration

**Files:**
- Modify: `app/collect.py` near `parse_jsonld` and `parse_city_html`
- Modify: `app/network.py` if URL validation needs a reusable public-image guard
- Test: `tests/test_collection.py`

**Interfaces:**
- Produce `extract_event_image(soup, item=None, page_url='') -> str | None` (or an equivalent focused helper) that returns one safe absolute URL.
- `parse_ical` preserves a safe `ATTACH` image URL, while `parse_jsonld` and both municipal HTML parsers pass `image_url` into `base_event` when a declared event image exists.

- [x] Write failing tests for JSON-LD image priority, Open Graph fallback, iCalendar attachments, absolute URL resolution, rejection of unsafe/favicons, and no-image output.
- [x] Run the focused tests and confirm they fail because image extraction is absent.
- [x] Implement the smallest helper and add `image_url` to event records without changing existing publication rules.
- [x] Run focused tests and the full Python suite; confirm all pass.

### Task 2: Frontend image presentation

**Files:**
- Modify: `web/src/main.tsx` `EventItem` type, event cards, and detail modal
- Modify: `web/src/style.css` for card/detail image layout and broken-image fallback
- Create: `web/src/image-url.mjs` for safe image URL selection
- Test: `web/src/image-url.test.mjs`

**Interfaces:**
- Render only a validated `http(s)` or same-origin `/api/` image URL.
- Keep images lazy-loaded and accessible with event-title alt text; hide the media block if loading fails.

- [x] Write a failing test for render URL safety/selection if a helper is introduced.
- [x] Run the focused frontend test and confirm the expected failure.
- [x] Implement optional card thumbnail and detail image with `loading="lazy"`, accessible alt text, and an `onError` fallback.
- [x] Run all frontend tests and the production build.

### Task 3: Data contract and documentation verification

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-09-14-darmstadt-local-design.md`
- Modify: `docs/research/2026-09-14-implementation-verification.md`
- Modify: `docs/superpowers/plans/2026-09-14-event-image-extraction.md`

- [x] Document the metadata-first behavior, remote hosting limitation, and no-OCR/no-crawling scope.
- [x] Mark completed plan steps and run JSON/shell/doc consistency checks.
- [x] Run `PYTHONPATH=. .venv/bin/pytest -q`, `(cd web && npm test && npm run build)`, and Python compilation before reporting completion.
