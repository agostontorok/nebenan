import { eventSearchHaystack } from "./filters.mjs";

export const SEMANTIC_MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2";
export const DEFAULT_SEMANTIC_THRESHOLD = 0.36;
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
  {
    threshold = DEFAULT_SEMANTIC_THRESHOLD,
    exactBoost = DEFAULT_EXACT_BOOST,
  } = {},
) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return [...events];
  return events
    .map((event) => {
      const exact = eventSearchHaystack(event).includes(normalizedQuery);
      const semantic = Number(scores?.[String(event.id)] ?? 0);
      return { event, exact, semantic, score: semantic + (exact ? exactBoost : 0) };
    })
    .filter(({ exact, semantic }) => exact || semantic >= threshold)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      const start =
        new Date(left.event.start).getTime() - new Date(right.event.start).getTime();
      if (start !== 0) return start;
      return String(left.event.id).localeCompare(String(right.event.id));
    })
    .map(({ event }) => event);
}

export function createSemanticSearchClient({ workerFactory } = {}) {
  const worker = workerFactory
    ? workerFactory()
    : new Worker(new URL("./semantic-search.worker.mjs", import.meta.url), {
        type: "module",
      });
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
    for (const request of pending.values()) {
      request.reject(error.error || new Error(error.message || "Semantic search failed"));
    }
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
      for (const request of pending.values()) {
        request.reject(new Error("Semantic search cancelled"));
      }
      pending.clear();
      worker.terminate();
    },
  };
}
