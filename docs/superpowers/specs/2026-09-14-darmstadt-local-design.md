# Darmstadt events portal — local first batch

## Purpose and agreed direction

Build a portal intended for public use, initially operated entirely on one computer. Collect events across Darmstadt, including small gatherings advertised by individual venues and larger city events. The portal combines a map, an event list, topic filters, and event-scale filters. Refresh collection weekly and expand the source directory over time.

Local operation means the application, database, collection jobs, and review tools run on the user's computer. Fetching event websites, supported social content, web search results, and map tiles still requires internet access. No deployment, cloud database, or public availability is part of this batch.

## Recommended approach

Use a local web application with a persistent SQLite database and a separate collector module sharing the application's data layer. Bind the server to localhost. Keep source-specific extraction separate from event validation and publication so sources can be added without changing the website.

A browser-only prototype cannot reliably perform collection or weekly updates. A hosted application can run continuously but is outside the user's requested first batch. A local application with its own collector provides the requested functionality and a path to later hosting.

## Visitor experience

- Open a responsive website on localhost; no visitor account is required.
- Browse real upcoming Darmstadt events in a synchronized map and list. Mobile users can switch between views.
- Use English as the default interface language with a German switch; remember the choice locally. Keep the map viewport after the initial fit while scheduled refreshes replace event markers.
- From every event detail, let a visitor enter attendee email addresses and download a local `.ics` calendar invitation that preserves timed or multi-day event dates, location, description, source URL, and cancellation status.
- Filter by date (today, weekend, week, or custom range), topic, scale, free admission when known, and text search.
- Topics include music, arts and culture, food and drink, games and social activities, sport and outdoors, family, learning, and civic events/demonstrations. Events can have multiple topics.
- Scale is independent of topic: small, medium, large, citywide, or unknown. Record whether classification comes from explicit source evidence or a reviewed estimate; do not invent attendance figures or infer scale solely from event type.
- Event details show the title, dates and times in Europe/Berlin, venue/address, short factual description, price when known, source links, last successful check, and cancellation status when confirmed.
- Show events with unresolved locations in the list without inventing map coordinates. Prefer known venue coordinates and cache address lookups.
- Use published routes for marches only when available; otherwise identify the published meeting point clearly.
- Keep small events discoverable through scale filters and a dedicated small-gatherings view.
- Let the local administrator edit published events, including topic tags, dates, location, event size, admission and cancellation state.

## Source collection and discovery

Maintain a source directory containing organiser/venue name, website and social links, collection method, enabled state, last attempt, last success, and errors. The initial three-source shortlist has been expanded through the [source-discovery report](../../research/2026-09-14-darmstadt-source-discovery.md) and [72-entry source registry](../../research/darmstadt-sources.json). Use its recommended integration order to select a balanced starting set of city, neighbourhood, specialist, and direct organiser sources. The registry remains the discovery record; adapters are marked active only after their actual pages are verified. The current local batch includes the Griesheim and Weiterstadt municipal calendars, while the Spielmobil route stays manual pending a stable feed.

Discovery identified working iCalendar exports, RSS/Atom feeds, and Event JSON-LD, as well as export limits, embedded contributor calendars, social-dependent announcements, and metadata inconsistencies. Track upstream calendar relationships so mirrors do not count as independent confirmations. Keep the publisher, organiser, venue, and individual event occurrence distinct. Validate feed horizons and recurring-event exceptions before relying on automatic publication.

Prefer structured event data and calendar feeds, then source-specific HTML extraction. Persist source URLs, declared image URLs, and evidence for extracted facts. Store multiple occurrences of recurring events separately and avoid extrapolating unspecified dates from old announcements. Image extraction remains bounded to already fetched pages; images are not downloaded or re-hosted.

Every weekly cycle checks enabled sources and seeks additional organiser or event pages through relevant outgoing links. Add candidate sources to the review screen rather than automatically following arbitrary links without bounds. Allow the administrator to add any website or social profile manually. Broad search-engine discovery uses an optional configured search provider; show when that capability is unconfigured, and do not label link discovery as a comprehensive web search.

Instagram and Facebook sources remain first-class entries in the directory, but automatic collection is enabled only for supported access methods actually configured and verified. An inaccessible social source is visibly marked as needing manual input. Provide a local intake form for an announcement URL, pasted text, or a poster plus event details. A URL or image alone does not guarantee readable content or a publishable event. Local OCR can assist when available; uncertain extracted facts require review. The batch does not promise universal social-account or Story coverage.

## Publication and review

Default proposed for this batch: publish events automatically only from enabled, trusted sources when required facts pass validation. Send incomplete, conflicting, or newly submitted events to a local review queue. The queue supports correcting details, assigning a venue and topics/scale, approving, rejecting, and recording cancellation. Provide a correction/submission form in the visitor interface; all such submissions require review.

Identify duplicates using source identifiers first, then normalized title, start time, and venue. Merge source references without merging separate performances. Prefer an organiser's explicit update over a secondary listing, and send unresolved conflicts for review.

A failed fetch must not delete existing events or imply cancellation. Record per-source failures and retain last-known information with its original check time. Missing or relative dates that cannot be resolved reliably remain unpublished. Treat fetched text as untrusted data, render it safely, and restrict collector requests to public web addresses with bounded timeouts, redirects, and response sizes.

## Weekly operation

- Offer a Run update now button and show the last run, next due time, source coverage, and failures.
- Run an initial collection explicitly during setup and subsequent scheduled checks every seven days while the application is running.
- Persist the schedule. On restart, run one catch-up cycle if overdue, rather than replaying every missed week.
- Prevent overlapping runs and isolate source failures so one unavailable website does not abort collection from other sources.
- Explain that updates pause when the application is stopped or the computer is asleep. Run status must not imply a weekly job ran when it did not.

## Acceptance and verification

1. Documented local setup starts the website and database without cloud credentials; database contents survive restart.
2. At least two independent real website sources successfully import dated events with provenance as a technical smoke check; this alone does not establish adequate event coverage. Use the discovery report to assess the proposed starting set across topics, neighbourhoods, and small gatherings, and report remaining gaps honestly.
3. Topic, scale, and date filters affect both map and list consistently. Unknown fields remain explicitly unknown.
4. Duplicate announcements merge while distinct recurring occurrences remain separate.
5. A failed source preserves existing records and surfaces a visible error. Uncertain announcements enter review and can be corrected and published.
6. Manual updates work; scheduling and overdue catch-up are verified using a controlled clock rather than waiting a week.
7. The interface is checked in desktop and mobile layouts. Empty results, loading, missing coordinates, and failed collection have usable states.
8. No example event is presented as a real collected listing. Optional search, social access, and OCR capabilities are visibly distinguished from working capabilities.

## Outside the first batch

Public hosting and production authentication, organiser accounts, email digests, ticket sales, mandatory paid APIs, and continuously running updates while the computer is off. Production security and operating requirements will be designed before exposing the application publicly.

## Sources examined during discovery

The expanded [source-discovery report](../../research/2026-09-14-darmstadt-source-discovery.md) includes 69 source entries, tested feed endpoints, a social-channel directory, and recommendations. It supersedes the preliminary list below as the source-selection reference.

- Darmstadt Tourismus: https://www.darmstadt-tourismus.de/events-und-maerkte.html
- Partyamt: https://www.events-in-darmstadt.de/
- Centralstation: https://www.centralstation-darmstadt.de/programm/
- Meta's Instagram API documentation: https://www.postman.com/meta/instagram/folder/u4g5a2a/instagram-api-with-facebook-login

## Review status

The public audience and local first batch are confirmed. Following expanded source discovery, the user requested the first implementation. The local implementation uses the proposed trusted-source publication default with an exception review queue. Eleven adapters are implemented, including the Griesheim and Weiterstadt municipal HTML calendars; the Das Rotzfreche Spielmobil is visible as a researched/manual source because its route is published as schedules and posters. Multi-day events retain their start and end instants as one listing, and the Admin view can edit published records. See the [implementation verification](../../research/2026-09-14-implementation-verification.md) and [neighbourhood expansion research](../../research/2026-09-14-expansion-sources.md).
