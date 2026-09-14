import { test } from "node:test";
import assert from "node:assert/strict";
import { berlinDay, dateRange, filterEvents } from "./filters.mjs";
test("Berlin day respects midnight and DST", () => {
  assert.equal(berlinDay("2026-03-28T23:30:00Z"), "2026-03-29");
  assert.equal(berlinDay("2026-10-24T22:30:00Z"), "2026-10-25");
});
test("seven days and weekend use local calendar days", () => {
  assert.deepEqual(dateRange("week", "2026-09-14"), [
    "2026-09-14",
    "2026-09-20",
  ]);
  assert.deepEqual(dateRange("weekend", "2026-09-20"), [
    "2026-09-19",
    "2026-09-20",
  ]);
});
test("all filters share inclusive Berlin dates; unknown locations remain", () => {
  const events = [
    {
      id: 1,
      title: "Jazz im Hof",
      start: "2026-09-14T23:30:00Z",
      topics: ["Musik"],
      scale: "small",
      free: true,
      lat: null,
    },
    {
      id: 2,
      title: "Jazz",
      start: "2026-09-14T12:00:00Z",
      topics: ["Musik"],
      scale: "small",
      free: true,
    },
    {
      id: 3,
      title: "Jazz",
      start: "2026-09-15T12:00:00Z",
      topics: ["Musik"],
      scale: "large",
      free: true,
    },
  ];
  assert.deepEqual(
    filterEvents(events, {
      from: "2026-09-15",
      to: "2026-09-15",
      query: "HOF",
      topic: "Musik",
      scale: "small",
      free: true,
    }).map((e) => e.id),
    [1],
  );
});

test("ongoing multi-day events overlap filters and all-day ends are exclusive", () => {
  const events = [
    {
      id: 1,
      title: "Festival",
      start: "2026-09-13T18:00:00+02:00",
      end: "2026-09-16T18:00:00+02:00",
    },
    {
      id: 2,
      title: "Ausstellung",
      start: "2026-09-13T00:00:00+02:00",
      end: "2026-09-15T00:00:00+02:00",
      all_day: true,
    },
    {
      id: 3,
      title: "Ausstellung läuft",
      start: "2026-09-13T00:00:00+02:00",
      end: "2026-09-16T00:00:00+02:00",
      all_day: true,
    },
  ];
  assert.deepEqual(
    filterEvents(events, { from: "2026-09-15", to: "2026-09-15" }).map(
      (e) => e.id,
    ),
    [3, 1],
  );
  assert.deepEqual(
    filterEvents(events, { from: "2026-09-16", to: "2026-09-14" }),
    [],
  );
});
