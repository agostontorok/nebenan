const searchableText = (event) =>
  [event.title, event.venue, event.address, event.description]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();

export function filterAdminEvents(events, query = "", limit = 100) {
  const needle = query.trim().toLocaleLowerCase();
  return events
    .filter((event) => event.status === "published")
    .filter((event) => !needle || searchableText(event).includes(needle))
    .slice()
    .sort((a, b) => String(a.start || "").localeCompare(String(b.start || "")))
    .slice(0, limit);
}
