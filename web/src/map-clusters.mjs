export function coordKey(lat, lon) {
  return `${lat.toFixed(5)},${lon.toFixed(5)}`;
}

export function cellSize(zoom) {
  return 0.0025 * Math.pow(2, 13 - zoom);
}

export function cellCenter(lat, lon, zoom) {
  const size = cellSize(zoom);
  const cellLat = Math.floor(lat / size) * size + size / 2;
  const cellLon = Math.floor(lon / size) * size + size / 2;
  return { lat: cellLat, lon: cellLon };
}

export function groupEvents(events, zoom) {
  const groups = new Map();
  for (const e of events) {
    if (e.lat == null || e.lon == null || !Number.isFinite(e.lat) || !Number.isFinite(e.lon)) continue;
    const { lat, lon } = cellCenter(e.lat, e.lon, zoom);
    const key = `${lat.toFixed(6)},${lon.toFixed(6)}`;
    let g = groups.get(key);
    if (!g) {
      g = { lat, lon, events: [] };
      groups.set(key, g);
    }
    g.events.push(e);
  }
  return [...groups.values()];
}

export function locationCount(events) {
  const keys = new Set();
  for (const e of events) {
    if (e.lat == null || e.lon == null || !Number.isFinite(e.lat) || !Number.isFinite(e.lon)) continue;
    keys.add(coordKey(e.lat, e.lon));
  }
  return keys.size;
}