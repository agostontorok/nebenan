const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function parseAttendees(value = "") {
  return [...new Set(
    String(value)
      .split(/[,;\s]+/)
      .map((item) => item.trim().toLocaleLowerCase())
      .filter((item) => EMAIL.test(item)),
  )];
}

export function icsEscape(value = "") {
  return String(value ?? "")
    .replaceAll("\\", "\\\\")
    .replaceAll(";", "\\;")
    .replaceAll(",", "\\,")
    .replaceAll(/\r?\n/g, "\\n");
}

function utcStamp(value) {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return "";
  return parsed.toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
}

function dateStamp(value) {
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime())) return "";
  // Event dates are stored as Berlin ISO values; use the calendar date in the
  // stored value rather than the browser's local timezone.
  return String(value).slice(0, 10).replaceAll("-", "");
}

function plusOneDay(value) {
  const parsed = new Date(`${String(value).slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(parsed.getTime())) return "";
  parsed.setUTCDate(parsed.getUTCDate() + 1);
  return parsed.toISOString().slice(0, 10).replaceAll("-", "");
}

export function eventToIcs(event, attendees = []) {
  const allDay = Boolean(event.all_day);
  const start = allDay ? dateStamp(event.start) : utcStamp(event.start);
  let end;
  if (allDay) {
    end = event.end ? dateStamp(event.end) : plusOneDay(event.start);
  } else {
    end = event.end ? utcStamp(event.end) : utcStamp(new Date(new Date(event.start).getTime() + 60 * 60 * 1000));
  }
  if (!start) throw new Error("This event has no valid start date");
  const location = [event.venue, event.address].filter(Boolean).join(", ");
  const sourceUrl = event.url || event.provenance?.[0]?.url || "";
  const stamp = utcStamp(new Date().toISOString());
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Darmstadt Local//Events//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:REQUEST",
    "BEGIN:VEVENT",
    `UID:${icsEscape(event.id || `${start}-${event.title || "event"}`)}@darmstadt.local`,
    `DTSTAMP:${stamp}`,
    allDay ? `DTSTART;VALUE=DATE:${start}` : `DTSTART:${start}`,
    end && (allDay ? `DTEND;VALUE=DATE:${end}` : `DTEND:${end}`),
    `SUMMARY:${icsEscape(event.title || "Darmstadt event")}`,
    location && `LOCATION:${icsEscape(location)}`,
    event.description && `DESCRIPTION:${icsEscape(event.description)}`,
    sourceUrl && `URL:${icsEscape(sourceUrl)}`,
    `STATUS:${event.cancelled ? "CANCELLED" : "CONFIRMED"}`,
    "SEQUENCE:0",
    ...parseAttendees(attendees.join ? attendees.join(",") : attendees).map(
      (email) => `ATTENDEE;CN=${icsEscape(email)};RSVP=TRUE:mailto:${email}`,
    ),
    "END:VEVENT",
    "END:VCALENDAR",
  ].filter(Boolean);
  return `${lines.join("\r\n")}\r\n`;
}
