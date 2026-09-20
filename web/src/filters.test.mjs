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
    filterEvents(
      events,
      {
        from: "2026-09-15",
        to: "2026-09-15",
        query: "HOF",
        topic: "Musik",
        scale: "small",
        free: true,
      },
      new Date("2026-09-17T12:00:00Z"),
    ).map((e) => e.id),
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
    filterEvents(
      events,
      { from: "2026-09-15", to: "2026-09-15" },
      new Date("2026-09-17T12:00:00Z"),
    ).map((e) => e.id),
    [3, 1],
  );
  assert.deepEqual(
    filterEvents(
      events,
      { from: "2026-09-16", to: "2026-09-14" },
      new Date("2026-09-17T12:00:00Z"),
    ),
    [],
  );
});

test("when the range starts today, events ended before now are dropped", () => {
  const events = [
    {
      id: 1,
      title: "Frühstück",
      start: "2026-09-14T06:00:00+02:00",
      end: "2026-09-14T11:00:00+02:00",
    },
    {
      id: 2,
      title: "Ausstellung",
      start: "2026-09-14T00:00:00+02:00",
      end: "2026-09-15T00:00:00+02:00",
      all_day: true,
    },
    {
      id: 3,
      title: "Konzert läuft gerade",
      start: "2026-09-14T14:00:00+02:00",
      end: "2026-09-14T19:00:00+02:00",
    },
    {
      id: 4,
      title: "Abendgottesdienst",
      start: "2026-09-14T18:00:00+02:00",
    },
  ];
  const now = new Date("2026-09-14T15:00:00+02:00");
  assert.deepEqual(
    filterEvents(events, { from: "2026-09-14", to: "2026-09-14" }, now).map(
      (e) => e.id,
    ),
    [2, 3, 4],
  );
  assert.deepEqual(
    filterEvents(
      events,
      { from: "2026-09-13", to: "2026-09-14" },
      now,
    ).map((e) => e.id),
    [2, 1, 3, 4],
  );
});
