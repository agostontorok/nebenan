# Neighbourhood expansion sources

The local collector now covers the two neighbouring municipalities requested
for the first public batch:

- [Stadt Griesheim events](https://www.griesheim.de/veranstaltungen) exposes dated
  occurrence cards. The collector keeps the listed date/time and links the
  occurrence page; when a card has no exact venue, it records Griesheim as the
  municipality and places an explicitly labelled approximate municipality-centre
  marker until an administrator confirms the exact location.
- [Stadt Weiterstadt appointments](https://www.weiterstadt.de/verwaltung-service/aktuelles/termine-veranstaltungen/index.php?y=2026)
  exposes year pages with start/end times, venues and descriptions in accordion
  entries. The parser understands ranges such as “02.10. – 05.10.26” and stores
  the actual end instant, so a multi-day festival remains one event spanning
  all of its days.
- [Das Rotzfreche SPIELMOBIL](https://spielmobil-darmstadt.de/spielmobil/) is
  recorded as a high-priority manual source. The [city information page](https://www.darmstadt.de/leben/soziales/kinder-und-jugendliche/kinder-und-jugendhaeuser)
  describes the free April–October route and links its Instagram profile, but a
  stable calendar feed was not found. Route dates therefore enter through the
  admin form or poster/link review rather than being invented as recurring
  events.

The original 69-source discovery registry remains the baseline research record;
these three additions are merged into the local database at startup. The
existing Heinerfest source remains in the registry and uses the same end-date
model for its multi-day festival dates.
