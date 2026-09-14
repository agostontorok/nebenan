import test from "node:test";
import assert from "node:assert/strict";
import { eventToIcs, parseAttendees } from "./calendar-invite.mjs";

const event = {
  id: "heinerfest-2026",
  title: "Heinerfest",
  start: "2026-07-02T18:00:00+02:00",
  end: "2026-07-06T23:00:00+02:00",
  all_day: false,
  venue: "Innenstadt",
  address: "64283 Darmstadt",
  description: "City festival; bring a friend,; and enjoy.",
  provenance: [{ url: "https://www.heinerfest.de/" }],
};

test("attendee input is normalized and de-duplicated", () => {
  assert.deepEqual(parseAttendees(" Alice@example.com, bob@example.org alice@example.com "), [
    "alice@example.com",
    "bob@example.org",
  ]);
});

test("calendar invite preserves the event range and attendees", () => {
  const ics = eventToIcs(event, ["alice@example.com"]);
  assert.match(ics, /METHOD:REQUEST/);
  assert.match(ics, /DTSTART:20260702T160000Z/);
  assert.match(ics, /DTEND:20260706T210000Z/);
  assert.match(ics, /ATTENDEE;CN=alice@example.com;RSVP=TRUE:mailto:alice@example.com/);
  assert.match(ics, /LOCATION:Innenstadt\\, 64283 Darmstadt/);
  assert.match(ics, /DESCRIPTION:City festival\\; bring a friend\\,\\; and enjoy\./);
  assert.match(ics, /URL:https:\/\/www\.heinerfest\.de\//);
});
