import { test } from "node:test";
import assert from "node:assert/strict";
import { eventPatch, berlinInput } from "./event-patch.mjs";

test("approval only changes status and leaves source date and cancellation unpinned", () => {
  const original = {
    title: "Konzert",
    start: "2026-09-18T19:00:00+02:00",
    cancelled: false,
    topics: ["music"],
    scale: "unknown",
    scale_evidence: "",
    status: "review",
  };
  const proposed = {
    ...original,
    scale_evidence: null,
    description: null,
    source_url: "https://example.org",
    status: "published",
  };
  assert.deepEqual(eventPatch(original, proposed), { status: "published" });
});
test("editing sends changed classification, explicit cleared values and changed cancellation only", () => {
  const original = {
    title: "Konzert",
    start: "2026-09-18T19:00:00+02:00",
    venue: "Hof",
    cancelled: false,
    topics: ["music", "culture"],
    scale: "unknown",
    scale_evidence: "",
    status: "review",
  };
  const proposed = {
    ...original,
    venue: null,
    topics: ["culture", "music"],
    scale: "small",
    scale_evidence: "20 seats according to source",
    cancelled: true,
  };
  assert.deepEqual(eventPatch(original, proposed), {
    venue: null,
    scale: "small",
    scale_evidence: "20 seats according to source",
    cancelled: true,
    status: "review",
  });
});

test("native Berlin date input formatting does not pin unchanged UTC or offset source dates", () => {
  const original = {
    start: "2026-09-18T17:30:00Z",
    end: "2026-09-18T21:00:00+02:00",
  };
  assert.deepEqual(
    eventPatch(original, {
      start: "2026-09-18T19:30",
      end: "2026-09-18T21:00",
      status: "published",
    }),
    { status: "published" },
  );
  assert.deepEqual(eventPatch(original, { start: "2026-09-18T20:30" }), {
    start: "2026-09-18T20:30",
  });
});

test("Berlin input defaults respect winter and summer independently of host time zone", () => {
  assert.equal(berlinInput("2026-01-18T17:30:15Z"), "2026-01-18T18:30:15");
  assert.equal(berlinInput("2026-09-18T17:30:00Z"), "2026-09-18T19:30:00");
  assert.equal(berlinInput(null), "");
});
