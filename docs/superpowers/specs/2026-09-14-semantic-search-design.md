# Semantic event search design

**Date:** 2026-09-14  
**Status:** Approved for planning

## Goal

Make the public event search useful for related wording. A query such as `fitness` should find an event titled `Zumba`, while preserving the existing exact search and event filters. Search must support German event text and English or German queries, and the first version must keep event text and inference local to the browser after the model is downloaded.

## Chosen approach

Use [Transformers.js](https://github.com/huggingface/transformers.js) in a Web Worker with the browser-ready [Xenova/paraphrase-multilingual-MiniLM-L12-v2](https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2) model. The model is loaded lazily on the first non-empty query and cached by the browser. It produces normalized sentence vectors; relevance is calculated with cosine similarity.

The model may be fetched from the model host the first time it is needed. No search query or event text is sent to a semantic-search service. The app remains usable with exact search while the model loads and if model initialization fails. A future deployment can self-host the same model by changing the model path and disabling remote models; that is outside this first implementation.

## Search data flow

1. The existing event list is filtered by date, topic, scale, and free-only criteria.
2. For each filtered event, the semantic worker receives a stable text projection containing title, topics, description, venue, address, and municipality.
3. The worker fingerprints that projection and caches its embedding in IndexedDB under the model version. Unchanged events reuse their vectors after a refresh.
4. The query is embedded once per changed query value.
5. The worker returns event IDs with similarity scores at or above a calibrated threshold.
6. The UI combines literal matches with semantic matches, gives literal matches a modest score boost, and sorts by relevance before start date.

The existing `filterEvents` behavior remains the lexical and filter baseline. Semantic matching is an additive query enhancement, so changing or clearing a query cannot bypass date, topic, scale, or free-only filters.

## Worker and module boundaries

- `semantic-search.mjs` owns model configuration, event text projection, fingerprints, similarity scoring, and a testable worker client interface.
- `semantic-search.worker.mjs` owns the Transformers.js pipeline and IndexedDB access. It accepts `index` and `query` messages and returns progress, ready, result, and error messages.
- `filters.mjs` continues to own synchronous date and lexical filtering. A small integration seam accepts semantic IDs/scores without making the date logic asynchronous.
- `main.tsx` owns query state, worker lifecycle, status copy, and rendering. It shows exact results immediately and merges semantic results when available.

## User experience

- The current search field remains the entry point; no extra mode switch is required.
- English and German status copy reports model loading, ready, and fallback states.
- Clearing the query immediately restores the normal date-sorted list and keeps the worker/model warm.
- The first-load status must make the sizable model download understandable without exposing implementation jargon.
- A model failure never blocks browsing, the map, admin editing, calendar invites, or other filters.

## Relevance policy

- Exact title, topic, venue, address, and description matches are always retained.
- Semantic matches are retained only above a threshold selected from positive and negative fixtures. The initial threshold is `0.36`, which admits measured `fitness → Zumba` and `fitness → Seniorengymnastik` similarities while excluding unrelated examples.
- Exact matches receive a modest boost, not an unconditional top position, so a strongly related result can still rank well.
- Events with missing text are excluded from embedding but remain available to lexical search.
- Ranking ties resolve by event start time, then event ID, to keep the UI stable.

## Error handling and privacy

The worker reports initialization and inference errors to the UI. The main thread keeps the last successful exact result set and switches to lexical-only mode for the current query. Errors are concise and diagnostic details stay in the browser console. Event text and query text stay in the browser; the only first-use network request is for model assets, which the browser cache reuses for later searches.

## Validation

- Unit tests cover text projection, fingerprint changes, cosine similarity, thresholding, exact-match boosting, and deterministic ordering.
- Worker-client tests use a deterministic fake embedder so CI does not download model assets.
- Existing filter tests continue to cover date overlap, multi-day events, topics, scale, free-only, and lexical matching.
- The frontend build must succeed without type errors.
- A browser smoke check verifies initial exact results, worker progress, semantic inclusion of `Zumba` for `fitness`, cached follow-up queries, English/German status text, and fallback when the model cannot load.

## Out of scope for this implementation

- Server-side vector databases or remote embedding APIs.
- Automatic translation of event text.
- Training or fine-tuning a Darmstadt-specific model.
- Semantic matching in the admin search field.
- Relevance analytics or user-specific ranking.
