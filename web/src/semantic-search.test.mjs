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
    { zumba: 0.71, fitness: 0.71, cinema: 0.31 },
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
