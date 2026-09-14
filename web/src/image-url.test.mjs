import test from "node:test";
import assert from "node:assert/strict";
import { safeImageUrl } from "./image-url.mjs";

test("safeImageUrl accepts public images and local submitted posters", () => {
  assert.equal(
    safeImageUrl("https://events.example/images/poster.jpg"),
    "https://events.example/images/poster.jpg",
  );
  assert.equal(safeImageUrl("/api/posters/event-123.jpg"), "/api/posters/event-123.jpg");
});

test("safeImageUrl rejects unsafe, private, and generic asset URLs", () => {
  for (const value of [
    "javascript:alert(1)",
    "data:image/png;base64,abc",
    "http://127.0.0.1/poster.jpg",
    "https://localhost/poster.jpg",
    "https://events.example/assets/site-logo.svg",
    "https://events.example/favicon.ico",
  ]) {
    assert.equal(safeImageUrl(value), "", value);
  }
});

test("safeImageUrl ignores empty values", () => {
  assert.equal(safeImageUrl(""), "");
  assert.equal(safeImageUrl(null), "");
});
