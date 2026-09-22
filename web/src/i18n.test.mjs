import { test } from "node:test";
import assert from "node:assert/strict";
import { languageFromBrowser, languageFromStorage, copy, topicLabels, scaleLabels } from "./i18n.mjs";

test("language preference accepts only supported languages", () => {
  assert.equal(languageFromStorage("de"), "de");
  assert.equal(languageFromStorage("en"), "en");
  assert.equal(languageFromStorage("fr"), "en");
  assert.equal(languageFromStorage(null), "en");
});

test("English and German have complete navigation and filter copy", () => {
  for (const lang of ["en", "de"]) {
    for (const key of ["nav.discover", "nav.sources", "nav.review", "filters.allTopics", "filters.allScales", "filters.freeOnly", "filters.semanticLoading", "filters.semanticReady", "filters.semanticFallback", "map.unknownLocation", "results.places", "results.placesDivider"]) {
      assert.ok(copy[lang][key], `${lang}.${key} is translated`);
    }
    assert.notEqual(topicLabels["en"].music, topicLabels["de"].music);
    assert.notEqual(scaleLabels["en"].unknown, scaleLabels["de"].unknown);
  }
});

test("languageFromBrowser uses stored preference before browser language", () => {
  assert.equal(languageFromBrowser("de"), "de");
  assert.equal(languageFromBrowser("en"), "en");
  assert.equal(languageFromBrowser("fr"), "en");
  assert.equal(languageFromBrowser(null), "en");
});

test("languageFromBrowser falls back to the browser language", () => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  try {
    Object.defineProperty(globalThis, "navigator", {
      value: { language: "de-DE" },
      configurable: true,
    });
    assert.equal(languageFromBrowser(null), "de");
    Object.defineProperty(globalThis, "navigator", {
      value: { language: "en-US" },
      configurable: true,
    });
    assert.equal(languageFromBrowser(null), "en");
    Object.defineProperty(globalThis, "navigator", {
      value: { language: "fr-FR" },
      configurable: true,
    });
    assert.equal(languageFromBrowser(null), "en");
  } finally {
    if (original) {
      Object.defineProperty(globalThis, "navigator", original);
    } else {
      delete globalThis.navigator;
    }
  }
});
