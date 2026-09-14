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
let activeRequestId = 0;
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
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("vectors")) {
        request.result.createObjectStore("vectors");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => resolve(null);
    request.onblocked = () => resolve(null);
  });
}

async function cachedVector(db, key) {
  if (memoryVectors.has(key)) return memoryVectors.get(key);
  if (!db) return null;
  try {
    return await new Promise((resolve) => {
      const request = db
        .transaction("vectors", "readonly")
        .objectStore("vectors")
        .get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

async function storeVector(db, key, vector) {
  memoryVectors.set(key, vector);
  if (!db) return;
  try {
    await new Promise((resolve) => {
      const request = db
        .transaction("vectors", "readwrite")
        .objectStore("vectors")
        .put(vector, key);
      request.onsuccess = () => resolve();
      request.onerror = () => resolve();
    });
  } catch {
    // Memory cache still keeps the current session usable.
  }
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
  activeRequestId = requestId;
  const allowed = new Set(allowedIds.map(String));
  try {
    self.postMessage({ type: "progress", requestId, phase: "loading", value: null });
    const db = await openVectorStore();
    const vectors = new Map();
    let indexed = 0;
    for (const event of events) {
      if (requestId !== activeRequestId) return;
      const text = eventSearchText(event);
      if (!text) continue;
      const key = `${SEMANTIC_MODEL_ID}:${event.id}:${textFingerprint(text)}`;
      vectors.set(String(event.id), await embed(text, db, key));
      indexed += 1;
      self.postMessage({
        type: "progress",
        requestId,
        phase: "indexing",
        value: indexed / Math.max(events.length, 1),
      });
    }
    const queryText = String(query).trim();
    if (!queryText) {
      self.postMessage({ type: "result", requestId, scores: {} });
      return;
    }
    const queryVector = await embed(
      queryText,
      db,
      `${SEMANTIC_MODEL_ID}:query:${textFingerprint(queryText)}`,
    );
    if (requestId !== activeRequestId) return;
    const scores = {};
    for (const [id, vector] of vectors) {
      if (allowed.has(id)) scores[id] = cosineSimilarity(queryVector, vector);
    }
    self.postMessage({ type: "result", requestId, scores });
  } catch (error) {
    if (requestId !== activeRequestId) return;
    self.postMessage({
      type: "error",
      requestId,
      message: error instanceof Error ? error.message : String(error),
    });
  }
};
