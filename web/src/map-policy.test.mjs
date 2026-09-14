import { test } from "node:test";
import assert from "node:assert/strict";
import { shouldFitInitialMap } from "./map-policy.mjs";

test("map auto-fit happens once when coordinates first appear", () => {
  assert.equal(
    shouldFitInitialMap({ hasFitted: false, coordinateCount: 3 }),
    true,
  );
  assert.equal(
    shouldFitInitialMap({ hasFitted: true, coordinateCount: 3 }),
    false,
  );
});

test("refreshes and marker changes preserve a user viewport", () => {
  assert.equal(
    shouldFitInitialMap({ hasFitted: true, coordinateCount: 8 }),
    false,
  );
  assert.equal(
    shouldFitInitialMap({ hasFitted: false, coordinateCount: 0 }),
    false,
  );
});
