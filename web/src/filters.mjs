export function berlinDay(value = new Date()) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "";
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Berlin",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
export function dateRange(mode, today = berlinDay()) {
  const date = new Date(today + "T12:00:00Z");
  const add = (n) => {
    const d = new Date(date);
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };
  if (mode === "today") return [today, today];
  if (mode === "weekend") {
    const weekday = date.getUTCDay();
    const offset = weekday === 0 ? -1 : 6 - weekday;
    return [add(offset), add(offset + 1)];
  }
  return [today, add(6)];
}
export function eventSearchHaystack(event) {
  return [
    event.title,
    event.venue,
    event.address,
    event.description,
    ...(event.topics || []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase("de");
}
export function filterEvents(events, f, now = Date.now()) {
  if (f.from && f.to && f.from > f.to) return [];
  const startsToday = f.from === berlinDay(now);
  return events
    .filter((e) => {
      const day = e.start ? berlinDay(e.start) : "";
      const endTime = e.end ? new Date(e.end).getTime() : NaN;
      const lasted =
        Number.isFinite(endTime) && endTime > new Date(e.start).getTime();
      const lastDay = lasted ? berlinDay(endTime - 1) : day;
      const endedSinceNow =
        startsToday &&
        lastDay === f.from &&
        Number.isFinite(endTime) &&
        endTime < now;
      const haystack = eventSearchHaystack(e);
      return (
        day &&
        !endedSinceNow &&
        (!f.from || lastDay >= f.from) &&
        (!f.to || day <= f.to) &&
        (!f.query || haystack.includes(f.query.toLocaleLowerCase("de"))) &&
        (!f.topic || (e.topics || []).includes(f.topic)) &&
        (!f.scale || e.scale === f.scale) &&
        (!f.free || e.free === true)
      );
    })
    .sort((a, b) => new Date(a.start) - new Date(b.start));
}
