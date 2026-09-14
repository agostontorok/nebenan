import test from "node:test";
import assert from "node:assert/strict";
import { filterAdminEvents } from "./admin-filter.mjs";

const events = [
  { id: "later", title: "Jazz night", venue: "Central station", address: "Darmstadt" , start: "2026-09-22T18:00:00+02:00", status: "published" },
  { id: "first", title: "Spielmobil", venue: "Griesheim park", address: "64347 Griesheim", start: "2026-09-15T15:00:00+02:00", status: "published" },
  { id: "review", title: "Draft", venue: "Weiterstadt", address: "64331 Weiterstadt", start: "2026-09-14T18:00:00+02:00", status: "review" },
];

test("admin list keeps published events and sorts by start", () => {
  assert.deepEqual(filterAdminEvents(events, "").map((event) => event.id), ["first", "later"]);
});

test("admin list searches title, venue and address", () => {
  assert.deepEqual(filterAdminEvents(events, "64347").map((event) => event.id), ["first"]);
  assert.deepEqual(filterAdminEvents(events, "jazz").map((event) => event.id), ["later"]);
});
