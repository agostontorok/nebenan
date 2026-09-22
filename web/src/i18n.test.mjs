import { test } from "node:test";
import assert from "node:assert/strict";
import { languageFromStorage, copy, topicLabels, scaleLabels } from "./i18n.mjs";

test("language preference accepts only supported languages", () => {
  assert.equal(languageFromStorage("de"), "de");
  assert.equal(languageFromStorage("en"), "en");
  assert.equal(languageFromStorage("fr"), "en");
  assert.equal(languageFromStorage(null), "en");
});

test("English and German have complete navigation and filter copy", () => {
  for (const lang of ["en", "de"]) {
    for (const key of ["nav.discover", "nav.sources", "nav.review", "filters.allTopics", "filters.allScales", "filters.freeOnly", "filters.semanticLoading", "filters.semanticReady", "filters.semanticFallback", "map.unknownLocation", "results.places", "results.placesDivider", "map.clearPlace"]) {
      assert.ok(copy[lang][key], `${lang}.${key} is translated`);
    }
    assert.notEqual(topicLabels["en"].music, topicLabels["de"].music);
    assert.notEqual(scaleLabels["en"].unknown, scaleLabels["de"].unknown);
  }
});
