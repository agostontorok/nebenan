// Compare form defaults without treating untouched blanks or topic order as edits.
function normalized(key, value) {
  if (key === "start" || key === "end") return berlinInput(value);
  if (key === "topics") return JSON.stringify([...(value || [])].sort());
  if (key === "all_day" || key === "cancelled") return Boolean(value);
  if (key === "scale") return value || "unknown";
  return value === "" || value == null ? null : value;
}
export function eventPatch(original, proposed) {
  const patch = {};
  for (const [key, value] of Object.entries(proposed)) {
    if (key === "source_url" || key === "poster") continue;
    if (
      key === "status" ||
      normalized(key, original[key]) !== normalized(key, value)
    ) {
      patch[key] = value;
    }
  }
  return patch;
}
export function berlinInput(value) {
  if (!value) return "";
  // datetime-local has no offset and is explicitly entered in Berlin time.
  const local = String(value).match(
    /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::(\d{2})(?:\.\d+)?)?$/,
  );
  if (local) return `${local[1]}T${local[2]}:${local[3] || "00"}`;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Berlin",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
}
