# Semantic Event Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local multilingual embedding search so related event terms such as `fitness` and `Zumba` match while all existing filters and exact search continue to work.

**Architecture:** Transformers.js runs the `Xenova/paraphrase-multilingual-MiniLM-L12-v2` ONNX model in a Web Worker. The worker caches event embeddings in IndexedDB and returns cosine-similarity scores; the React app merges those scores with the existing synchronous lexical/date/topic/scale/free filtering and falls back to lexical search on any model error.

**Tech Stack:** Vite, React 19, TypeScript, Node test runner, `@huggingface/transformers`, ONNX Runtime Web, Web Worker, IndexedDB.

## Global Constraints

- Keep event and query text in the browser; no remote semantic-search API.
- Fetch the model lazily on the first non-empty query and rely on browser caching after that first download.
- Preserve exact lexical matches and the current date, topic, scale, free-only, multi-day, and map behavior.
- Support English and German status copy through the existing `i18n.mjs` dictionaries.
- Do not load or download model weights in automated tests.
- Semantic matching is for the public discover search only; admin search remains lexical.
- Use the existing project commands: `npm test`, `npm run build`, and `PYTHONPATH=. .venv/bin/pytest -q`.

## File map

- Create `web/src/semantic-search.mjs`: pure text projection, fingerprinting, cosine scoring, relevance ranking, and the injectable worker client.
- Create `web/src/semantic-search.worker.mjs`: Transformers.js pipeline, IndexedDB vector cache, worker message protocol, and progress/error reporting.
- Create `web/src/semantic-search.test.mjs`: deterministic tests for pure helpers and a fake-worker client.
- Modify `web/src/filters.mjs`: export the shared lexical haystack helper and use it from `filterEvents`.
- Modify `web/src/filters.test.mjs`: prove the shared helper preserves current exact matching.
- Modify `web/src/main.tsx`: initialize the client lazily, search the filtered event set, merge semantic scores, and render status text.
- Modify `web/src/i18n.mjs`: add English and German semantic-search status strings.
- Modify `web/src/style.css`: style the live semantic status beside the search field and its loading/fallback states.
- Modify `web/package.json` and `web/package-lock.json`: add the Transformers.js dependency.
- Modify `README.md`: document first-use model download, browser caching, local inference, and lexical fallback.

### Task 1: Define deterministic semantic primitives

**Files:**
- Create: `web/src/semantic-search.mjs`
- Create: `web/src/semantic-search.test.mjs`
- Modify: `web/src/filters.mjs`
- Modify: `web/src/filters.test.mjs`

**Interfaces:**
- `normalizeSearchText(value: unknown): string` returns lowercase, accent-insensitive whitespace-normalized text.
- `eventSearchText(event: Record<string, unknown>): string` returns the joined searchable event fields.
- `textFingerprint(value: string): string` returns a stable non-cryptographic fingerprint for cache keys.
- `cosineSimilarity(a: ArrayLike<number>, b: ArrayLike<number>): number` returns a value in `[-1, 1]` and returns `0` for invalid or zero-length vectors.
- `rankSemanticMatches(events: EventLike[], query: string, scores: Record<string, number>, options?: { threshold?: number; exactBoost?: number }): EventLike[]` retains exact matches or scores above the threshold and sorts by boosted score, start time, and ID.
- `eventSearchHaystack(event: Record<string, unknown>): string` is the shared lexical haystack used by both exact filtering and semantic ranking.

- [ ] **Step 1: Write failing tests for normalization, projection, cosine, and ranking**

Add to `web/src/semantic-search.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeSearchText,
  eventSearchText,
  textFingerprint,
  cosineSimilarity,
  rankSemanticMatches,
} from "./semantic-search.mjs";

const event = (id, title, start, extra = {}) => ({
  id,
  title,
  start,
  topics: [],
  venue: "",
  address: "",
  description: "",
  ...extra,
});

test("normalizes German text and whitespace", () => {
  assert.equal(normalizeSearchText("  FÜR   Kinder\n"), "fur kinder");
  assert.equal(normalizeSearchText(null), "");
});

test("projects searchable event fields and changes its fingerprint", () => {
  const text = eventSearchText(
    event("zumba", "Zumba im Bürgerpark", "2026-09-15T18:00:00+02:00", {
      topics: ["Sport"],
      description: "Tanz und Bewegung für alle",
      area: "Darmstadt",
    }),
  );
  assert.match(text, /zumba im burgerpark/);
  assert.match(text, /sport/);
  assert.match(text, /darmstadt/);
  assert.notEqual(textFingerprint(text), textFingerprint(`${text} geändert`));
});

test("cosine similarity handles aligned, opposite, and invalid vectors", () => {
  assert.equal(cosineSimilarity([1, 0], [1, 0]), 1);
  assert.equal(cosineSimilarity([1, 0], [-1, 0]), -1);
  assert.equal(cosineSimilarity([0, 0], [1, 0]), 0);
  assert.equal(cosineSimilarity([1], [1, 0]), 0);
});

test("semantic ranking keeps exact fitness matches and related Zumba", () => {
  const events = [
    event("zumba", "Zumba im Bürgerpark", "2026-09-15T18:00:00+02:00"),
    event("fitness", "Fitnesskurs für Einsteiger", "2026-09-16T18:00:00+02:00"),
    event("cinema", "Filmabend", "2026-09-14T20:00:00+02:00"),
  ];
  const ranked = rankSemanticMatches(
    events,
    "fitness",
    { zumba: 0.71, fitness: 0.59, cinema: 0.88 },
    { threshold: 0.7, exactBoost: 0.08 },
  );
  assert.deepEqual(ranked.map(({ id }) => id), ["fitness", "zumba"]);
});

test("ranking is stable for equal scores", () => {
  const events = [
    event("later", "Later", "2026-09-18T18:00:00+02:00"),
    event("earlier", "Earlier", "2026-09-17T18:00:00+02:00"),
  ];
  assert.deepEqual(
    rankSemanticMatches(events, "sport", { later: 0.8, earlier: 0.8 }).map(
      ({ id }) => id,
    ),
    ["earlier", "later"],
  );
});
```

- [ ] **Step 2: Run the focused tests and verify the expected RED state**

Run `cd web && node --test src/semantic-search.test.mjs`.

Expected result: FAIL because `semantic-search.mjs` and its exported functions do not exist yet. Do not continue until the failure is caused by the missing feature rather than a test syntax error.

- [ ] **Step 3: Implement the pure helpers and shared lexical haystack**

Create `web/src/semantic-search.mjs` with these implementations:

```js
import { eventSearchHaystack } from "./filters.mjs";

export const SEMANTIC_MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
export const DEFAULT_SEMANTIC_THRESHOLD = 0.42;
export const DEFAULT_EXACT_BOOST = 0.08;

export function normalizeSearchText(value) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("de-DE")
    .replace(/\s+/g, " ")
    .trim();
}

export function eventSearchText(event) {
  return normalizeSearchText(
    [
      event?.title,
      event?.venue,
      event?.address,
      event?.area,
      event?.description,
      ...(Array.isArray(event?.topics) ? event.topics : []),
    ]
      .filter(Boolean)
      .join(" "),
  );
}

export function textFingerprint(value) {
  let hash = 2166136261;
  for (const character of String(value ?? "")) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}

export function cosineSimilarity(a, b) {
  if (!a || !b || a.length === 0 || a.length !== b.length) return 0;
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i += 1) {
    const left = Number(a[i]);
    const right = Number(b[i]);
    if (!Number.isFinite(left) || !Number.isFinite(right)) return 0;
    dot += left * right;
    normA += left * left;
    normB += right * right;
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / Math.sqrt(normA * normB);
}

export function rankSemanticMatches(
  events,
  query,
  scores,
  { threshold = DEFAULT_SEMANTIC_THRESHOLD, exactBoost = DEFAULT_EXACT_BOOST } = {},
) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return [...events];
  return events
    .map((event) => {
      const exact = eventSearchHaystack(event).includes(normalizedQuery);
      const semantic = Number(scores?.[String(event.id)] ?? 0);
      return { event, exact, score: semantic + (exact ? exactBoost : 0) };
    })
    .filter(({ exact, score }) => exact || score - exactBoost >= threshold)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      const start = new Date(left.event.start).getTime() - new Date(right.event.start).getTime();
      if (start !== 0) return start;
      return String(left.event.id).localeCompare(String(right.event.id));
    })
    .map(({ event }) => event);
}
```

In `web/src/filters.mjs`, extract the existing haystack construction into the exported helper below and replace the inline construction with a call to it:

```js
export function eventSearchHaystack(event) {
  return [
    event.title,
    event.venue,
    event.address,
    event.description,
    ...(event.topics || []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("de");
}
```

- [ ] **Step 4: Run the focused tests and the existing filter tests**

Run `cd web && node --test src/semantic-search.test.mjs src/filters.test.mjs`.

Expected result: PASS for the new normalization, projection, cosine, ranking, and existing date/lexical tests.

- [ ] **Step 5: Commit the primitive layer**

Run:

```bash
git add web/src/semantic-search.mjs web/src/semantic-search.test.mjs web/src/filters.mjs web/src/filters.test.mjs
git commit -m "test: define semantic search primitives"
```

### Task 2: Add the local embedding worker and client

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/semantic-search.mjs`
- Create: `web/src/semantic-search.worker.mjs`
- Modify: `web/src/semantic-search.test.mjs`

**Interfaces:**
- `createSemanticSearchClient(options?: { workerFactory?: () => Worker }): SemanticSearchClient` returns `{ search(events, query, allowedIds, handlers?): Promise<Record<string, number>>, dispose(): void }`.
- `search` sends raw event objects, a normalized query, and allowed event IDs; `handlers.onProgress({ phase: string, value: number | null })` is optional.
- The worker accepts `{ type: "search", requestId, events, query, allowedIds }` and returns `progress`, `result`, or `error` messages carrying the same `requestId`.

- [ ] **Step 1: Add a failing fake-worker protocol test**

Append to `web/src/semantic-search.test.mjs`:

```js
import { createSemanticSearchClient } from "./semantic-search.mjs";

test("worker client resolves the newest result and forwards progress", async () => {
  const messages = [];
  const worker = {
    onmessage: null,
    onerror: null,
    postMessage(message) {
      messages.push(message);
      queueMicrotask(() => worker.onmessage({ data: { type: "progress", requestId: message.requestId, phase: "loading", value: 0.5 } }));
      queueMicrotask(() => worker.onmessage({ data: { type: "result", requestId: message.requestId, scores: { zumba: 0.81 } } }));
    },
    terminate() {},
  };
  const progress = [];
  const client = createSemanticSearchClient({ workerFactory: () => worker });
  const scores = await client.search(
    [{ id: "zumba", title: "Zumba", start: "2026-09-15T18:00:00+02:00" }],
    "fitness",
    ["zumba"],
    { onProgress: (update) => progress.push(update) },
  );
  assert.deepEqual(scores, { zumba: 0.81 });
  assert.equal(progress[0].phase, "loading");
  assert.equal(messages[0].type, "search");
  client.dispose();
});
```

- [ ] **Step 2: Run the protocol test and verify RED**

Run `cd web && node --test src/semantic-search.test.mjs`.

Expected result: FAIL because `createSemanticSearchClient` is not exported yet.

- [ ] **Step 3: Add the dependency and implement the injectable client**

Run `cd web && npm install @huggingface/transformers` to update both package manifests.

Extend `web/src/semantic-search.mjs` with a client that uses a module worker in production and the injected worker in tests:

```js
export function createSemanticSearchClient({ workerFactory } = {}) {
  const worker = workerFactory
    ? workerFactory()
    : new Worker(new URL("./semantic-search.worker.mjs", import.meta.url), { type: "module" });
  let requestId = 0;
  const pending = new Map();
  worker.onmessage = ({ data }) => {
    const request = pending.get(data.requestId);
    if (!request) return;
    if (data.type === "progress") {
      request.onProgress?.({ phase: data.phase, value: data.value ?? null });
      return;
    }
    pending.delete(data.requestId);
    if (data.type === "result") request.resolve(data.scores || {});
    else request.reject(new Error(data.message || "Semantic search failed"));
  };
  worker.onerror = (error) => {
    for (const request of pending.values()) request.reject(error.error || new Error(error.message));
    pending.clear();
  };
  return {
    search(events, query, allowedIds, { onProgress } = {}) {
      const id = ++requestId;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject, onProgress });
        worker.postMessage({ type: "search", requestId: id, events, query, allowedIds });
      });
    },
    dispose() {
      for (const request of pending.values()) request.reject(new Error("Semantic search cancelled"));
      pending.clear();
      worker.terminate();
    },
  };
}
```

- [ ] **Step 4: Implement the worker pipeline, cache, and protocol**

Create `web/src/semantic-search.worker.mjs` with these boundaries:

```js
import { env, pipeline } from "@huggingface/transformers";
import {
  SEMANTIC_MODEL_ID,
  cosineSimilarity,
  eventSearchText,
  textFingerprint,
} from "./semantic-search.mjs";

env.useBrowserCache = true;
env.cacheKey = "nebenan-semantic-search-v1";

let extractorPromise;
const memoryVectors = new Map();

function extractor() {
  extractorPromise ||= pipeline("feature-extraction", SEMANTIC_MODEL_ID);
  return extractorPromise;
}

function vectorFromOutput(output) {
  return Array.from(output.data || []);
}

function openVectorStore() {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  return new Promise((resolve) => {
    const request = indexedDB.open("nebenan-semantic-search", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("vectors");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
  });
}

async function cachedVector(db, key) {
  if (!db) return memoryVectors.get(key) || null;
  return new Promise((resolve) => {
    const request = db.transaction("vectors", "readonly").objectStore("vectors").get(key);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => resolve(null);
  });
}

async function storeVector(db, key, vector) {
  memoryVectors.set(key, vector);
  if (!db) return;
  await new Promise((resolve) => {
    const request = db.transaction("vectors", "readwrite").objectStore("vectors").put(vector, key);
    request.onsuccess = request.onerror = () => resolve();
  });
}

async function embed(text, db, key) {
  const cached = await cachedVector(db, key);
  if (cached) return cached;
  const output = await (await extractor())(text, { pooling: "mean", normalize: true });
  const vector = vectorFromOutput(output);
  await storeVector(db, key, vector);
  return vector;
}

self.onmessage = async ({ data }) => {
  if (data.type !== "search") return;
  const { requestId, events = [], query = "", allowedIds = [] } = data;
  const allowed = new Set(allowedIds.map(String));
  try {
    self.postMessage({ type: "progress", requestId, phase: "loading", value: null });
    const db = await openVectorStore();
    const vectors = new Map();
    let indexed = 0;
    for (const event of events) {
      const text = eventSearchText(event);
      if (!text) continue;
      const key = `${SEMANTIC_MODEL_ID}:${event.id}:${textFingerprint(text)}`;
      vectors.set(String(event.id), await embed(text, db, key));
      indexed += 1;
      self.postMessage({ type: "progress", requestId, phase: "indexing", value: indexed / Math.max(events.length, 1) });
    }
    const queryText = String(query).trim();
    if (!queryText) {
      self.postMessage({ type: "result", requestId, scores: {} });
      return;
    }
    const queryVector = await embed(`query: ${queryText}`, db, `${SEMANTIC_MODEL_ID}:query:${textFingerprint(queryText)}`);
    const scores = {};
    for (const [id, vector] of vectors) {
      if (allowed.has(id)) scores[id] = cosineSimilarity(queryVector, vector);
    }
    self.postMessage({ type: "result", requestId, scores });
  } catch (error) {
    self.postMessage({ type: "error", requestId, message: error instanceof Error ? error.message : String(error) });
  }
};
```

The worker must ignore unknown messages, return an empty score object for an empty query, keep cached vectors keyed by model/event/fingerprint, and report errors without throwing out of the message handler.

- [ ] **Step 5: Run all frontend tests and verify GREEN**

Run `cd web && npm test`.

Expected result: all existing tests plus the semantic helper and fake-worker tests pass without fetching model assets.

- [ ] **Step 6: Commit the worker layer**

Run:

```bash
git add web/package.json web/package-lock.json web/src/semantic-search.mjs web/src/semantic-search.worker.mjs web/src/semantic-search.test.mjs
git commit -m "feat: add local semantic search worker"
```

### Task 3: Integrate semantic results into the discover view

**Files:**
- Modify: `web/src/main.tsx`
- Modify: `web/src/i18n.mjs`
- Modify: `web/src/style.css`

**Interfaces:**
- `baseFiltered` is the existing event list with `query: ""`, so semantic results cannot bypass date/topic/scale/free filters.
- `lexicalFiltered` remains the current `filterEvents` result with the user query and is rendered while semantic search is pending or unavailable.
- `semanticScores: Record<string, number> | null` is replaced only by the latest request; stale worker responses are ignored by the client request ID and effect cancellation.

- [ ] **Step 1: Add bilingual copy and a failing UI-state test**

Add these keys to both dictionaries in `web/src/i18n.mjs`:

```js
"filters.semanticLoading": "Finding related events locally…",
"filters.semanticReady": "Related matches included",
"filters.semanticFallback": "Exact search only (local model unavailable)",
```

Use the German equivalents:

```js
"filters.semanticLoading": "Ähnliche Veranstaltungen werden lokal gesucht …",
"filters.semanticReady": "Ähnliche Treffer eingeschlossen",
"filters.semanticFallback": "Nur exakte Suche (lokales Modell nicht verfügbar)",
```

Extend `web/src/i18n.test.mjs` to assert these three keys exist and are non-empty in both languages. Run `cd web && node --test src/i18n.test.mjs` and verify RED before changing the test fixture if the keys are not yet present.

- [ ] **Step 2: Add semantic client state and preserve the lexical baseline**

In `web/src/main.tsx`, import `createSemanticSearchClient` and `rankSemanticMatches`. Add `semanticClientRef`, `semanticScores`, and `semanticStatus` state near the existing query state. Replace the single `filtered` memo with:

```tsx
const baseFiltered = useMemo(
  () => filterEvents(events, { from, to, query: "", topic, scale, free }) as EventItem[],
  [events, from, to, topic, scale, free],
);
const lexicalFiltered = useMemo(
  () => filterEvents(events, { from, to, query, topic, scale, free }) as EventItem[],
  [events, from, to, query, topic, scale, free],
);
const [semanticScores, setSemanticScores] = useState<Record<string, number> | null>(null);
const [semanticStatus, setSemanticStatus] = useState<"idle" | "loading" | "ready" | "fallback">("idle");
const filtered = useMemo(() => {
  if (!query.trim() || !semanticScores) return lexicalFiltered;
  return rankSemanticMatches(baseFiltered, query, semanticScores) as EventItem[];
}, [baseFiltered, lexicalFiltered, query, semanticScores]);
```

Add an effect that lazily creates one client, clears stale scores, keeps lexical results visible, and applies only the current request:

```tsx
useEffect(() => {
  if (!query.trim()) {
    setSemanticScores(null);
    setSemanticStatus("idle");
    return;
  }
  let cancelled = false;
  setSemanticScores(null);
  setSemanticStatus("loading");
  semanticClientRef.current ||= createSemanticSearchClient();
  semanticClientRef.current
    .search(events, query, baseFiltered.map((event) => String(event.id)), {
      onProgress: () => {
        if (!cancelled) setSemanticStatus("loading");
      },
    })
    .then((scores: Record<string, number>) => {
      if (cancelled) return;
      setSemanticScores(scores);
      setSemanticStatus("ready");
    })
    .catch(() => {
      if (!cancelled) setSemanticStatus("fallback");
    });
  return () => {
    cancelled = true;
  };
}, [events, query, baseFiltered]);

useEffect(() => () => semanticClientRef.current?.dispose(), []);
```

Initialize `semanticClientRef` with `useRef<any>(null)` alongside the other refs. Keep the admin memo unchanged so admin search remains lexical.

- [ ] **Step 3: Run focused tests and the TypeScript build**

Run `cd web && npm test && npm run build`.

Expected result: all tests pass and Vite/TypeScript accepts the worker URL and semantic state integration.

- [ ] **Step 4: Render the bilingual live status**

Place this immediately after the existing search label in the discover filter bar:

```tsx
{query.trim() && (
  <span className={`semantic-status semantic-${semanticStatus}`} role="status" aria-live="polite">
    {semanticStatus === "loading"
      ? tr("filters.semanticLoading")
      : semanticStatus === "ready"
        ? tr("filters.semanticReady")
        : tr("filters.semanticFallback")}
  </span>
)}
```

Add to `web/src/style.css`:

```css
.semantic-status {
  align-self: center;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}
.semantic-ready {
  color: #54765d;
}
.semantic-fallback {
  color: #a3452e;
}
@media (max-width: 760px) {
  .semantic-status {
    flex-basis: 100%;
    white-space: normal;
  }
}
```

- [ ] **Step 5: Commit the discover integration**

Run:

```bash
git add web/src/main.tsx web/src/i18n.mjs web/src/i18n.test.mjs web/src/style.css
git commit -m "feat: integrate semantic event filtering"
```

### Task 4: Document operation and verify the complete application

**Files:**
- Modify: `README.md`
- Modify: `docs/research/2026-09-14-implementation-verification.md` only if the existing verification artifact records feature behavior.

- [ ] **Step 1: Add the local semantic-search section to the README**

Document that the public discover search uses a multilingual MiniLM embedding model in a browser worker, downloads model assets on first use, caches those assets and event vectors locally, and falls back to exact search if the browser cannot initialize Transformers.js. State that the admin search remains lexical and that model weights are not downloaded by automated tests.

- [ ] **Step 2: Run complete automated verification**

Run each command separately from the repository root:

```bash
cd web && npm test
cd web && npm run build
PYTHONPATH=. .venv/bin/pytest -q
.venv/bin/python -m py_compile app/*.py
bash -n run.sh
```

Expected result: all frontend tests pass, the Vite build succeeds, all backend tests pass, Python compilation succeeds, and the shell syntax check exits successfully.

- [ ] **Step 3: Run the browser smoke check against the local server**

Start the existing local server with `./run.sh`, open the discover view, and verify:

1. With no query, result ordering and counts match the pre-feature behavior.
2. Enter `fitness`; exact results appear immediately, then the status changes from loading to ready and a `Zumba` event appears when its score clears the threshold.
3. Change the query quickly from `fitness` to `music`; only the latest query’s results remain.
4. Switch EN/DE while a query is active; the status text changes language.
5. Disable model loading in the browser or simulate a worker error; exact results remain visible and the fallback status appears.
6. Reload and search again; the cached model does not restart a full download.
7. Date, topic, scale, free-only, map, admin, calendar invite, and event image behavior remain functional.

- [ ] **Step 4: Commit the documentation and verification notes**

Run:

```bash
git add README.md docs/research/2026-09-14-implementation-verification.md
git commit -m "docs: document local semantic search"
```

## Self-review checklist

- The spec’s local browser-worker architecture is covered by Tasks 1–2.
- Lazy first-use loading, browser caching, IndexedDB event vectors, and lexical fallback are covered by Tasks 2–3.
- Exact matching, filter preservation, stable relevance ranking, and bilingual status copy are covered by Tasks 1 and 3.
- No task requires model weights during CI; the worker test uses an injected fake worker.
- No placeholders, TODOs, or unspecified APIs are used; every cross-file interface is named above.
