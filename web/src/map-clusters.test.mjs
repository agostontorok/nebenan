import { test } from "node:test";
import assert from "node:assert/strict";
import {
  coordKey,
  cellSize,
  cellCenter,
  groupEvents,
  locationCount,
} from "./map-clusters.mjs";

const ev = (id, lat, lon) => ({ id, lat, lon, title: `E${id}` });

test("coordKey collapses float representation and is stable", () => {
  assert.equal(coordKey(49.8728, 8.6512), "49.87280,8.65120");
  assert.equal(coordKey(49.8728, 8.6512), coordKey(49.8728, 8.6512));
});

test("cellSize halves as zoom increases and is finite", () => {
  const s13 = cellSize(13);
  assert.ok(s13 > 0);
  assert.equal(cellSize(14), s13 / 2);
  assert.equal(cellSize(16), s13 / 8);
  assert.ok(Number.isFinite(cellSize(19)));
});

test("identical coordinates share one cell at every zoom", () => {
  for (let z = 10; z <= 19; z++) {
    const groups = groupEvents(
      [ev(1, 49.8728, 8.6512), ev(2, 49.8728, 8.6512), ev(3, 49.8728, 8.6512)],
      z,
    );
    assert.equal(groups.length, 1);
    assert.equal(groups[0].events.length, 3);
  }
});

test("nearby distinct coordinates separate at deeper zooms", () => {
  const a = ev(1, 49.8728, 8.6512);
  const b = ev(2, 49.8729, 8.6513);
  const coarse = groupEvents([a, b], 13);
  assert.equal(coarse.length, 1);
  const fine = groupEvents([a, b], 17);
  assert.equal(fine.length, 2);
});

test("far apart coordinates never share a cell", () => {
  const groups = groupEvents(
    [ev(1, 49.87, 8.65), ev(2, 49.76, 8.59)],
    10,
  );
  assert.equal(groups.length, 2);
});

test("locationCount counts distinct coordinate pairs", () => {
  assert.equal(locationCount([ev(1, 49.87, 8.65), ev(2, 49.87, 8.65), ev(3, 49.76, 8.59)]), 2);
});

test("cellCenter places the point inside its own cell", () => {
  const { lat, lon } = cellCenter(49.8728, 8.6512, 13);
  assert.ok(Math.abs(lat - 49.8728) < cellSize(13));
  assert.ok(Math.abs(lon - 8.6512) < cellSize(13));
});