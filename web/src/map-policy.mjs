export function shouldFitInitialMap({ hasFitted, coordinateCount }) {
  return !hasFitted && coordinateCount > 0;
}
