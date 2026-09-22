export const MAX_DRIFT_ZOOM = 19;

export function shouldFitInitialMap({ hasFitted, coordinateCount }) {
  return !hasFitted && coordinateCount > 0;
}
