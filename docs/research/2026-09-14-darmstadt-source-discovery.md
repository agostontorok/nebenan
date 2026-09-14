# Darmstadt event-source discovery

The strongest foundation for a Darmstadt event portal is a combination of city calendars, neighbourhood calendars, and direct organiser programmes, with social channels tracked alongside them. Small events are not confined to Instagram: several community organisations already publish usable calendar feeds. Social media remains important for exact dates, late changes, temporary venues, and announcements that never reach the larger calendars.

This inventory contains **69 source entries**. It includes organisers, venues, aggregators, editorial directories, and a known mirror; it is not a claim of 69 independent feeds. Public pages were retrieved for **67 entries**. Two candidates remain unresolved because direct HTTPS verification failed. Checks were made on **14 September 2026**. The machine-readable [source registry](darmstadt-sources.json) records the source URLs, collection recommendations, limitations, and website-linked social URLs.

**22 feed endpoints were checked: 13 returned nonempty iCalendar data, eight returned nonempty RSS/Atom data, and one returned an empty response.** These are endpoints, not independent sources: some are alternative exports from the same publisher. No application collector has been implemented, and raw feed-record counts do not measure unique upcoming events. The [feed evidence](2026-09-14-feed-probe.json) preserves the response types, record counts, observed date bounds, and check timestamps.

## Findings that change the initial design

### Neighbourhood calendars deserve early integration

Nachbarschaftsheim, Eberstädter Bürgerverein, Lincoln-Siedlung, and Postsiedlung all returned readable iCalendar data. These are valuable sources of local gatherings, practical activities, and community programmes. They would materially broaden a starting set of Partyamt, Centralstation, and the city calendar. [Nachbarschaftsheim](https://nbh-darmstadt.de/veranstaltungen-aktuell/), [Eberstadt](https://www.eberstaedter-buergerverein.de/veranstaltungen/liste/), [Lincoln](https://www.lincoln-darmstadt.de/events/), [Postsiedlung](https://www.postsiedlung.de/events/).

Kranichstein's portal combines multiple contributing calendars. Its embed contains 18 calendar IDs, six of which represent holidays or week numbers rather than local organisers. Two of the remaining calendars returned public iCalendar data; the other ten have not been tested individually. Ingestion should preserve which contributing calendar supplied an event, exclude the six non-event calendars, and check time interpretation: the website itself warns about displayed times. [In Kranichstein Aktiv](https://www.kranichsteinkalender.de/).

### Social announcements complement websites in different ways

Bruchbude explicitly states Monday quiz and Tuesday bingo times on its website, while directing readers to Instagram for exact dates of its fortnightly Single Night. This is a concrete case where a website can describe a series without anchoring the next occurrence. The collector should distinguish an explicit weekly rule from an unanchored fortnightly rule. [Bruchbude events](https://bruchbudedarmstadt.de/events/).

Bad Habits Run Club directs readers to Instagram and Strava for upcoming runs and warns that locations may vary. Treat the website as identity and context, and the dated announcement as evidence of where a specific run starts. An Sibin illustrates another format: its website has multiple poster images, while the extracted text describes music, karaoke, and quizzes without a complete dated programme. [Bad Habits](https://www.asphaltgold.com/pages/badhabits-run-club), [An Sibin](https://www.ansibin.de/).

There should therefore be separate statuses for a discovered social account, readable content, a usable dated announcement, and a working authorised collection method. A website link to Instagram proves neither account type nor API availability. Meta's documented Instagram API with Facebook Login excludes consumer accounts; it should not be treated as universal public-account access. [Meta's API documentation](https://www.postman.com/meta/instagram/folder/u4g5a2a/instagram-api-with-facebook-login).

### Source independence must be tracked

P's current website links directly to the Partyamt calendar. P's original articles still add venue and organiser discovery value, but the calendar does not provide a second independent confirmation. Familien willkommen explicitly states that its family events are supplied from the city's calendar in cooperation with ztix. The city calendar itself links to ztix event details. [P Magazin](https://www.p-stadtkultur.de/), [Familien willkommen](https://www.familien-willkommen.de/Termine), [city calendar](https://www.darmstadt.de/veranstaltungskalender).

Keep **publisher, organiser, venue, upstream calendar, and occurrence** separate. A single screening may be promoted by its organiser, its venue, and several calendars. Conversely, the same organiser may run events in several places. Centralstation's Wanderkino programme and the corresponding Knabenschule listing demonstrate why the organiser's usual address cannot determine the map pin. [Centralstation programme](https://www.centralstation-darmstadt.de/programm/), [Knabenschule programme](https://www.knabenschule.de/).

### Structured data still needs validation

Goldene Krone's landing page contained 100 Event objects. Its metadata offers a promising collection route, but some venues are room labels with an empty postal address, and some records have equal start and end times. Use a verified venue record and do not present an unknown duration as a zero-minute event. [Goldene Krone](https://www.goldene-krone.de/).

A Nachbarschaftsheim event's structured metadata represented a zero price with USD currency. This does not establish an admission charge in dollars; compare the readable event information before publishing currency. FRIZZ provides coordinates in some structured venue records, but its results also include online events. Coordinates, attendance mode, prices, and dates need field-level checks. [Nachbarschaftsheim](https://nbh-darmstadt.de/veranstaltungen-aktuell/), [FRIZZ calendar](https://www.frizzmag.de/search/event/veranstaltungs-kalender/).

### Live pages can disagree with search extracts

The live 806qm programme returned upcoming October and December 2026 entries, while the search reader returned an older empty programme. Golden Leaves' live homepage had already moved to its 2027 edition while older indexed pages still described 2026. CSD's homepage announced 2027 alongside navigation to its 2026 programme and route. Search results are useful for discovery; publication should use the current source page and an explicit edition/year. [806qm](https://806qm.de/programm/), [Golden Leaves](https://goldenleavesfestival.de/), [CSD Darmstadt](https://www.csd-darmstadt.de/).

## Verified collection routes

The counts below describe the returned response at check time. They include historical events, recurrence definitions, and overrides where present. They must not be added together or described as this week's event supply. Date bounds in the evidence files use event DTSTART values, excluding timezone definitions, and do not expand recurrences.

| Publisher / endpoint | Observed response | Implication |
|---|---|---|
| [FRIZZ iCal](https://www.frizzmag.de/search/event/veranstaltungs-kalender/calendar.ics) | 96 VEVENT records; recurrence and exclusions present | Combine bounded recurrence expansion with city/online filtering. |
| [FRIZZ event RSS](https://www.frizzmag.de/search/event/veranstaltungs-kalender/index.rss) | 30 items | Alternative discovery route, not 30 extra independent events. |
| [Nachbarschaftsheim iCal](https://nbh-darmstadt.de/veranstaltungen/?ical=1) | 30 records, starts from 14–18 September 2026 | Returned horizon is short; inspect export coverage and pagination. |
| [Eberstadt default iCal](https://www.eberstaedter-buergerverein.de/veranstaltungen/?ical=1) | Two records | A successful response can still omit most listed events. |
| [Eberstadt list iCal](https://www.eberstaedter-buergerverein.de/veranstaltungen/liste/?ical=1) | 11 records through 19 December 2026 | Preferred tested export; matched the list count. |
| [Lincoln iCal](https://www.lincoln-darmstadt.de/events/?ical=1) | 30 records through 30 October 2026 | Strong initial candidate; assess the 30-record boundary. |
| [Postsiedlung iCal](https://www.postsiedlung.de/events/?ical=1) | 15 records, starts from 14–19 September 2026 | Useful current-week feed; compare with next-week calendar navigation. |
| [Jazzinstitut iCal](https://www.jazzinstitut.de/jazzkalender/?ical=1) | 30 records through 28 November 2026 | Good specialist coverage; deduplicate partner-venue listings. |
| [vielbunt calendar](https://www.vielbunt.org/kalender/) | Public iCal: 2,982 records, including history, recurrences, and overrides | Filter and expand a bounded window; preserve changed/cancelled instances. |
| [Kranichstein calendars](https://www.kranichsteinkalender.de/) | Two tested public feeds: 213 and 193 records | Test the remaining contributors; historical DTSTART does not prove a recurring series has ended. |
| [Transition Town](https://transition-darmstadt.de/) | Two category exports: 68 and 541 records | Preserve category scope and merge overlapping occurrences. |
| [Schader event export](https://www.schader-stiftung.de/veranstaltungen/aktuell/artikel/film-im-forum-der-lange-februar/ical) | One VEVENT, served as application/octet-stream | Follow the index to individual exports; inspect content rather than relying solely on MIME type. |
| [TU public-event RSS](https://www.tu-darmstadt.de/universitaet/aktuelles_meldungen/veranstaltungen_6/veranstaltungen_rss.de.jsp) | Ten items | Dates can be inside descriptions; fetch details and check the list horizon. |
| [Moller Haus upcoming_events](https://theatermollerhaus.de/upcoming_events) | 129 RSS items; sample was a production with a run date range | Discover productions, then extract individual performances. |
| [HoffART event RSS](https://www.hoffart-theater.de/veranstaltungen/feed/) | Ten items; sampled item had publication time and empty description | Useful change discovery, insufficient by itself for event timing. |
| [CCC RSS](https://chaos-darmstadt.de/feed.xml) | 92 news items | Classify event announcements separately from general news. |
| [806qm RSS](https://806qm.de/feed/) | Two news items | Use the programme for event coverage. |
| [Repair-Cafés export page](https://www.repaircafes-darmstadt.de/index.php/kalender/export-im-ical-format) | Linked event RSS and Atom each returned five items; iCal generation form inspected | Event feeds are readable; the generated iCal export remains untested. |
| [Wixhausen advertised iCal](https://vereint.wixhausen.org/veranstaltungen/?ical=1) | HTTP 200, zero bytes | Not a working feed in this check; use the readable calendar or investigate further. |

The three Google export URLs were derived from calendar IDs openly embedded by the source websites, then fetched successfully. Their exact URLs are in the [feed evidence](2026-09-14-feed-probe.json). No authenticated social API, private calendar, or private group was accessed.

## Recommended integration order

The **21 priority-one entries** form a balanced candidate set for the local portal. This is an integration recommendation, not a claim that their adapters are built or that all 21 should be enabled without validation.

**First wave — reusable feed and structured-data support:** Nachbarschaftsheim, Eberstädter Bürgerverein, Lincoln, Postsiedlung, vielbunt, Kranichstein, Transition Town, FRIZZ, Goldene Krone, Jazzinstitut, TU Darmstadt, and Schader-Stiftung. This tests iCalendar, recurrence overrides, RSS discovery, embedded calendars, and Event JSON-LD against real sources while including substantial small-event coverage.

**Second wave — fill gaps with source-specific extraction:** Partyamt, the city calendar, Centralstation, Knabenschule, Oetinger Villa, Bruchbude, Repair-Cafés, Stadtbibliothek, and ADFC. These add broad discovery, pub activities, independent culture, neighbourhood reading groups, and outdoor activities. Repair-Cafés already has a readable event RSS route; it is placed here to complete its geographic and export checks.

**Then expand by missing topic and district:** theatre, museums, literature, food and wine, school-holiday programmes, international gatherings, and seasonal festivals. Prefer a new organiser adding a missing kind of event over a further mirror of events already collected. Use P, the city directories, the queer scene guide, and regional calendars to find those organisers.

The first three-source proposal should therefore be broadened. Two successful imports are a useful technical smoke check, but they do not demonstrate the breadth required for this portal. A first useful dataset should demonstrate citywide discovery, several neighbourhoods, at least one small social activity, family/community activities, culture, and outdoors/science, with gaps clearly visible.

## Social-channel directory

The registry records **83 distinct normalized social-link URLs across 47 source entries**. These are website-linked URLs, not 83 independently verified accounts or 83 usable APIs. Some identify the same organisation on multiple platforms; others point to partner, statewide, or corporate accounts. The following selection is particularly useful for source discovery and small-event follow-up. Profile content and collection access remain untested.

| Organiser | Website-linked social channel | Reason to track |
|---|---|---|
| [Bruchbude](https://bruchbudedarmstadt.de/events/) | [Instagram](https://www.instagram.com/bruchbude_darmstadt/) | Exact dates for the otherwise unanchored fortnightly series. |
| [An Sibin](https://www.ansibin.de/) | [Instagram](https://www.instagram.com/ansibindarmstadt/), [Facebook](https://www.facebook.com/pg/ansibindarmstadt) | Dated poster announcements. |
| [Bad Habits](https://www.asphaltgold.com/pages/badhabits-run-club) | [Instagram](https://www.instagram.com/badhabitsrunclub/), [Strava](https://www.strava.com/clubs/badhabits) | Specific run dates and variable meeting points. |
| [Café Bellevue](https://cafe-bellevue.com/) | [Instagram](https://www.instagram.com/cafebellevuedarmstadt/) | Small cultural and informal gatherings. |
| [Weststadtcafé](https://www.weststadtcafe.de/) | [Instagram](https://www.instagram.com/weststadtcafe/) | Seasonal announcements and follow-up. |
| [OHA/Osthang](https://www.osthang.de/) | [Instagram](https://www.instagram.com/oha.osthang/), [Facebook](https://www.facebook.com/OHAOsthang/) | Current location and programme context. |
| [Schlosskeller](https://www.schlosskeller-darmstadt.de/) | [Instagram](https://instagram.com/schlosskellerdarmstadt/) | Cultural programme and organiser discovery. |
| [Goldene Krone](https://www.goldene-krone.de/) | [Instagram](https://www.instagram.com/goldenekronedarmstadt/) | Supplement its structured programme. |
| [Knabenschule](https://www.knabenschule.de/) | [Instagram](https://www.instagram.com/kulturzentrum_knabenschule/) | Programme and participating organisers. |
| [Galerie Kurzweil](https://www.krzwl.de/) | [Instagram](https://www.instagram.com/galeriekurzweil/) | Promoters and club-night announcements. |
| [Keller-Klub](https://www.keller-klub.de/) | [Instagram](https://www.instagram.com/kuenstlerkeller/) | Smaller cultural evenings. |
| [Nachbarschaftsheim](https://nbh-darmstadt.de/veranstaltungen-aktuell/) | [Instagram](https://instagram.com/nachbarschaftsheim_darmstadt/) | Workshops and community programme. |
| [Arheilger Stadtteilverein](https://www.arheilger-stadtteilverein.de/) | [Instagram](https://www.instagram.com/arheilgerstadtteilverein/) | Neighbourhood announcements. |
| [VereinT für Wixhausen](https://wixhausen.org/) | [Instagram](https://www.instagram.com/vereintfuerwixhausen/) | Club and neighbourhood programme. |
| [Makerspace](https://makerspace-darmstadt.de/) | [Instagram](https://instagram.com/makerspacedarmstadt/) | Workshop announcements. |
| [Transition Town](https://transition-darmstadt.de/) | [Instagram](https://www.instagram.com/transition_town_darmstadt/) | Community initiatives. |
| [ADFC](https://www.adfc-darmstadt.de/) | [Instagram](https://www.instagram.com/adfcdarmstadtdieburg/) | Regional rides; filter individual departure locations. |
| [Fridays for Future](https://darmstadtforfuture.de/) | [Instagram](https://instagram.com/fridaysforfuture.da/) | Local action announcements. |
| [vinocentral](https://www.vinocentral.de/termine/) | [Instagram](https://www.instagram.com/vinocentral_/) | Tastings, music and food events. |
| [P Magazin](https://www.p-stadtkultur.de/) | [Instagram](https://www.instagram.com/pmagazin_da/) | New venues and organisers, not independent calendar confirmation. |

## How to keep discovering sources every week

Maintain a queue of candidate organisers independently from the event queue. Each weekly run should revisit known calendars, inspect new programme links, and search combinations of district, activity, and date. Example discovery terms include Darmstadt Kneipenquiz, Kranichstein Nachbarschaft Termine, Arheilgen Frühstückstreff, Eberstadt Backtag, Wixhausen Vereinsfest, Darmstadt Lesekreis, Spieleabend, offene Werkstatt, Jam Session, Lauftreff, Vernissage, and Sprachcafé. Searches should include the current month/year when useful, but an indexed date must still be checked against the page.

A candidate becomes a source only after establishing its identity, actual geographic coverage, and an event-bearing channel. Store where the lead came from and whether it adds new organisers, topics, or districts. A venue-hire page or a café's opening hours can remain in the venue directory without generating events. Discover organisers from existing announcements and ticket links as well as from venue homepages: the cultural programme often belongs to a collective using several venues.

Measure added coverage using unique upcoming occurrences, new organisers, district/topic coverage, successful-check age, and a small audit of missed events from selected social accounts. Feed item counts and website counts are poor substitutes. No numerical recall estimate is justified until a reference sample of real announcements is compared with collected events.

The requested weekly cycle is a reasonable discovery baseline, but it cannot guarantee timely coverage of short-notice announcements. Treffbunt says its next time and location are announced about a week ahead, and the national Fridays for Future listing says local strike information can remain incomplete until Thursday. Keep weekly updates as the agreed baseline; a more frequent check of selected active sources is a later option if missed-event measurements warrant it. [Treffbunt](https://www.vielbunt.org/treffbunt/), [Fridays for Future dates](https://fridaysforfuture.de/streiktermine/).

## Remaining gaps and constraints

- **Social-only organisers:** linked accounts have been identified, but their complete current post/Story coverage and API eligibility have not been audited. Invitations behind private accounts or groups are outside this inventory.
- **Calendar scope:** only two of Kranichstein's 12 potential event-contributor calendars were tested. Several other feeds have response limits or narrow date horizons. A nonempty feed is not proof of completeness.
- **Neighbourhood gaps:** Kranichstein, Bessungen, Arheilgen, Eberstadt, Wixhausen, Lincoln, and Postsiedlung now have candidate sources. Smaller informal groups, migrant associations, independent studios, dance schools, churches beyond the sampled film/youth programmes, and sports clubs still need additional discovery.
- **Identity and location:** similarly named places can be outside Darmstadt. Galerie Kurzweil's verified site is KRZWL; the similarly named Alfeld gallery is unrelated. Eberstadt municipality results are not automatically Darmstadt-Eberstadt events.
- **Public participation:** student-only activities, invitation-only conferences, members' sessions, courses requiring registration, and restricted-audience support programmes must retain their participation conditions. Publicly visible advertising is not the same as unrestricted attendance.
- **Event scale:** most sampled listings describe venue, format, and programme rather than expected attendance. Keep scale unknown unless supported by source evidence or a reviewed estimate. A venue's total capacity, a club's membership, or an account's followers are not event attendance.
- **Source availability:** BUND Darmstadt's legacy domain and the Martinsviertel association failed direct TLS checks. Wixhausen's advertised feed was empty. These are specific unresolved paths, not proof the organisations are inactive.
- **Reuse:** publish factual summaries with original links. Treat posters as extraction inputs unless their reuse is permitted; supported access must be checked before enabling automatic social collection.

## Full source inventory and references

Each linked title below identifies the publishing organisation and exact entry page assessed. The common access date is 14 September 2026; page publication dates vary or are not stated. Collection routes are recommendations based on observed HTML, feeds, and metadata. The registry marks all adapters as researched, not implemented.

### City calendars and discovery

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [Partyamt](https://www.events-in-darmstadt.de/) | City and surrounding area; small social events through concerts | HTML occurrence pages | Treat partyamt.de as an alias, not another independent source. Filter out surrounding towns. |
| [Wissenschaftsstadt Darmstadt calendar](https://www.darmstadt.de/veranstaltungskalender) | Culture, civic, family and accessible events across the city | HTML listings and linked ztix details | City submission asks for 14 days lead time; insufficient alone for spontaneous events. |
| [P Stadtkulturmagazin](https://www.p-stadtkultur.de/) | Small venues, collectives, new places and cultural recommendations | Editorial articles and outbound source links | Its calendar links to Partyamt. Articles add discovery value; calendar overlap is not independent corroboration. |
| [FRIZZ regional calendar](https://www.frizzmag.de/search/event/veranstaltungs-kalender/) | Arts, family, nightlife, workshops across the region | Verified iCal/RSS and Event JSON-LD | Regional and online records require filtering; calendar includes recurring masters from earlier years. |
| [Familien willkommen](https://www.familien-willkommen.de/Termine) | Family selection of city-calendar events | Use for category cross-checks | Explicitly reuses the city calendar with ztix; do not count as an independent feed. |
| [City leisure and holiday directory](https://www.darmstadt.de/leben/soziales/kinder-und-jugendliche/freizeit-und-ferien) | Youth providers and holiday programmes | Follow official provider links | Separates local activities from trips elsewhere; directory is not itself a complete dated programme. |

### Music, nightlife and performance

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [Centralstation](https://www.centralstation-darmstadt.de/programm/) | Concerts, comedy, children and events at partner venues | HTML programme and event details | Organiser is not always the event venue; Wanderkino uses multiple locations. |
| [Bessunger Knabenschule](https://www.knabenschule.de/) | Concerts, flea markets, film, theatre and regular groups | HTML programme plus groups pages | List repeats summaries in detail sections; preserve door time, start time and rain-location notes separately. |
| [Goldene Krone](https://www.goldene-krone.de/) | Pub music, table-football tournaments, parties and concerts | Event JSON-LD plus details | 100 Event objects observed on the landing page; room labels can lack a street address. No attendance inference. |
| [Schlosskeller](https://www.schlosskeller-darmstadt.de/) | Student culture, jazz, karaoke, queer parties and film | HTML programme and details | Overview sometimes omits year or start time; enrich each event before publication. |
| [Oetinger Villa](https://oetingervilla.de/) | Independent concerts, community meals and open meetings | HTML dated programme plus explicit recurrence rules | Some meetings alternate online and in-person; one fixed venue cannot be assumed for all occurrences. |
| [806qm](https://806qm.de/programm/) | Student culture, music and small creative gatherings | Current HTML programme; news RSS as discovery | Live HTML had upcoming October/December 2026 events while the search reader showed an old empty page. |
| [Galerie Kurzweil / KRZWL](https://www.krzwl.de/) | Club nights and comedy | HTML programme and organiser-linked ticket pages | galeriekurzweil.de without a hyphen is an unrelated gallery in Alfeld. Use verified KRZWL identity. |
| [HoffART](https://www.hoffart-theater.de/veranstaltungen/) | Small concerts, readings, dance and theatre | HTML event dates; RSS for discovery | RSS sample contained publication time and empty event descriptions; pubDate is not event start time. |
| [Keller-Klub / Künstlerkeller](https://www.keller-klub.de/) | Readings, music and cultural evenings | Follow programme from homepage | Distinct from Schlosskeller despite sharing the castle setting; homepage RSS is not a proven event feed. |
| [Staatstheater Darmstadt](https://www.staatstheater-darmstadt.de/spielplan/) | Theatre, opera, dance, concerts and family tours | HTML schedule with individual performances | Preserve sold-out state, age recommendations, price ranges and separate performance dates. |
| [Theater Moller Haus](https://theatermollerhaus.de/) | Independent theatre and children's performances | Production RSS for discovery, then performance details | The upcoming_events RSS returned production records; a run's date range is not a continuous event. |
| [Jazzinstitut Darmstadt Jazzkalender](https://www.jazzinstitut.de/jazzkalender/) | Jazz across multiple local venues, jams and workshops | Event JSON-LD and iCal | Includes partner venues such as vinocentral; use actual performance venue and deduplicate. |

### Pubs, food and informal gatherings

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [Bruchbude](https://bruchbudedarmstadt.de/events/) | Quiz, bingo and social evenings | Explicit website recurrence; social confirmation for ambiguous series | Monday quiz 19:00 and Tuesday bingo 20:30 are stated; fortnightly Single Night dates are directed to Instagram. |
| [An Sibin](https://www.ansibin.de/) | Pub quiz, karaoke and live music | Website posters plus linked Instagram/Facebook | Text extraction alone misses poster content. Conflicting quiz weekdays exist in secondary listings; verify occurrence. |
| [GastSpielhaus](https://www.gastspielhaus-darmstadt.de/) | Board-game venue at Riegerplatz | Track announcements; add venue to discovery directory | A permanent game collection and opening hours are not dated organised events. |
| [Weststadtcafé](https://www.weststadtcafe.de/) | Seasonal outdoor gatherings and dance | Website programme and linked Instagram | Seasonal venue. Do not confuse with the separate Weststadt Bar domain. |
| [Ponyhof Darmstadt](https://www.ponyhof-darmstadt.de/) | Occasional public gatherings and food events | Public announcements and linked Facebook | Website heavily promotes private-event hire; exclude private bookings and generic venue offers. |
| [Café Bellevue](https://cafe-bellevue.com/) | Collective café, cultural events and informal gatherings | Website announcements and linked Instagram/Facebook | Do not treat permanent exhibitions or an invitation to propose events as dated appointments. |
| [vinocentral](https://www.vinocentral.de/termine/) | Wine tastings, music and food events | HTML dates, linked details and social announcements | Some events take place elsewhere; cross-check jazz overlap and preserve booking requirements. |

### Neighbourhoods and community

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [Nachbarschaftsheim Darmstadt](https://nbh-darmstadt.de/veranstaltungen-aktuell/) | Bessungen; crafts, movement, family and intergenerational activities | Verified iCal and Event JSON-LD | Several locations. Export sample ends that Friday; inspect horizon. A zero-price metadata sample used USD. |
| [In Kranichstein Aktiv](https://www.kranichsteinkalender.de/) | Kranichstein providers, clubs, family and community activities | Public Google calendar feeds per contributing calendar | 18 embedded calendar IDs include 6 holidays/week-number calendars. Two event calendars tested; remaining contributors untested. Site warns of displayed-time issues. |
| [VereinT für Wixhausen](https://wixhausen.org/) | Wixhausen clubs, Kerb, concerts and neighbourhood gatherings | HTML calendar; advertised iCal needs investigation | Advertised iCal returned HTTP 200 with zero bytes. Visible listings include cancellations and events in Griesheim. |
| [Arheilger Stadtteilverein](https://www.arheilger-stadtteilverein.de/) | Arheilgen neighbourhood activities | Website announcements and linked Instagram | Inspect dated posts and posters; no structured event feed identified on the sampled homepage. |
| [Bezirksverein Martinsviertel](https://www.martinsviertel-darmstadt.de/) | Neighbourhood fairs, markets, music and open-air cinema | Candidate from search; direct HTTPS needs resolution | Direct fetch failed certificate verification. Keep disabled pending a verified accessible source; do not disable TLS checks. |
| [Eberstädter Bürgerverein](https://www.eberstaedter-buergerverein.de/veranstaltungen/liste/) | Eberstadt; baking days, concerts, walks and markets | Event JSON-LD; compare list and default iCal exports | Default export returned two events versus eleven on the list. Use Darmstadt-Eberstadt, not the separate municipality eberstadt.de. |
| [Muckerhaus Arheilgen](https://www.muckerhaus.de/) | Community breakfasts, family activities and local meetings | HTML calendar with dated event pages | Contains support services as well as activities; distinguish appointments from public leisure events. |
| [Lincoln-Siedlung](https://www.lincoln-darmstadt.de/) | Neighbourhood meetups, families, youth and community programmes | Verified iCal plus /events/ HTML | Retain organiser and audience restrictions; not every meeting is open to all visitors. |
| [Zusammen in der Postsiedlung](https://postsiedlung.de/) | Neighbourhood cafés, meals, markets and social activities | Verified iCal plus current news | Specific invitations may have residency or eligibility conditions. News also includes reports of past events. |

### Community, civic and sustainability

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [vielbunt and Treffbunt](https://www.vielbunt.org/kalender/) | Queer social gatherings, sport, community and civic events | Verified public Google iCal; linked news and social channels | Large feed mixes history, recurring masters and overrides. Preserve stated participation/age requirements without inferring attendee identities. |
| [Transition Town Darmstadt](https://transition-darmstadt.de/) | Sustainability, community projects, cooking, film and demonstrations | Two verified category-specific iCal feeds | Substantial history and recurrence data; category subsets can overlap and do not represent upcoming-event counts. |
| [Fridays for Future Darmstadt](https://darmstadtforfuture.de/) | Local demonstrations and open organising meetings | Dated blog posts, explicit recurrence and official Instagram | Separate a local event from travel to a demonstration elsewhere; old campaign pages remain indexed. |
| [BUND Darmstadt](https://darmstadt.bund.net/nc/termine/) | Nature activities and open environmental meetings | Candidate from indexed calendar; resolve HTTPS access | Direct fetch failed hostname certificate verification; alternative BUND Hessen source is readable. |
| [BUND Zentrum für Stadtnatur](https://www.bund-hessen.de/stadtnaturzentrum/) | Nature workshops, talks and children's environmental activities | HTML dates and linked programme | BUND Hessen social profiles are statewide, not a Darmstadt event feed; filter online and out-of-city entries. |
| [Repair-Cafés Darmstadt](https://www.repaircafes-darmstadt.de/) | Practical repair gatherings at multiple neighbourhood venues | Verified event RSS/Atom; iCal generation form available | RSS sample held five events; iCal form was inspected but generated calendar not tested. Region and cancellation categories matter. |

### Learning, science and technology

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [Makerspace Darmstadt](https://makerspace-darmstadt.de/) | Open workshop and making community | Explicit weekly website schedule plus announcements | Public workshop Thursdays 19:00–about 21:00 is distinct from members' 24/7 access. |
| [CCC Darmstadt](https://chaos-darmstadt.de/) | Open technology meetings, user groups and talks | Verified news RSS and event-linked posts | Feed includes news and old posts, not only events. Door-status text is not event cancellation. |
| [TU Darmstadt public calendar](https://www.tu-darmstadt.de/universitaet/aktuelles_meldungen/veranstaltungen_6/index_1.de.jsp) | Public science, talks, workshops and exhibitions | Verified RSS; linked detail pages; iCal support documented | RSS sample returned ten items. Exclude online-only/nonpublic sessions from the city map; dates can be inside descriptions. |
| [Schader-Stiftung](https://www.schader-stiftung.de/veranstaltungen/aktuell) | Society, public discussion, science and cultural events | HTML index and verified per-event iCal | One export is one event, not the whole calendar. Some events are invitation-only or use multiple venues. |
| [vhs Darmstadt](https://www.darmstadt-vhs.de/programm) | Workshops, talks, creative activities and learning | HTML course listings and details | Separate single events from multi-session courses; retain registration, language and online status. |
| [h_da Sprachcafé](https://international.h-da.de/internationalisation/sprachcafe) | Language exchange and international gatherings | Dated institutional page and linked social channel | Check semester dates, participant eligibility and campus; h_da also has locations outside Darmstadt. |
| [Studierendenwerk intercultural events](https://studierendenwerkdarmstadt.de/interkulturelles/events/) | International social activities and excursions | Programme page and dated details | Programme explicitly targets enrolled h_da/TU students; do not label it unrestricted public access. |

### Arts, museums, literature and film

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [Stadtbibliothek Darmstadt](https://www.darmstadt.de/leben/bildung/stadtbibliothek/veranstaltungen-und-termine) | Reading circles, family activities and library events | HTML event/series details | Includes neighbourhood branches; map the branch, not always Justus-Liebig-Haus. |
| [Literaturhaus Darmstadt](https://www.literaturhaus-darmstadt.de/programm/filter?action_filter=Suchen) | Readings, writing, talks and programmes of resident associations | HTML programme; PDF supplementary | Separate the main programme from resident organisers; PDFs can lag behind the current web programme. |
| [Hessisches Landesmuseum Darmstadt](https://www.hlmd.de/de/besuchen/kalender/) | Tours, workshops, family activities and exhibitions | Calendar HTML and dated details | Exhibition ranges and timed tours are different event types; no JSON-LD found on sampled calendar page. |
| [Mathildenhöhe Darmstadt](https://www.mathildenhoehe.de/besuch/termine) | Art tours, after-work events, workshops and exhibitions | HTML dated programme | Different activities share the site; extract actual meeting location and access conditions. |
| [Studentischer Filmkreis](https://filmkreis.de/programm/aktuell) | Curated screenings and student film culture | HTML programme; RSS discovery link found | Semester gaps are possible. Filmkreis and Rex may announce the same screening. |
| [Programmkino Rex](https://www.kinopolis.de/rx/angebote/programmuebersicht-rex/20) | Cinema, special screenings and partner film series | Programme pages and linked screening details | Distinguish cinema schedules from special events. Linked Instagram is the national Kinopolis account. |
| [AlleWeltKino / Dekanat Darmstadt](https://dekanat-darmstadt.de/arbeitsbereiche/bildung-und-gesellschaft/alleweltkino) | Themed film series and cultural discussion | Series page and programme download | Often overlaps Rex screenings; verify individual dates and year before import. |

### Sport, outdoors and family

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [ADFC Darmstadt-Dieburg](https://www.adfc-darmstadt.de/) | Bike tours, repair workshops and cycling community | HTML tours and linked event records | District-wide coverage; use departure point and participant requirements, not organiser address. |
| [Bad Habits Run Club](https://www.asphaltgold.com/pages/badhabits-run-club) | Social running around Darmstadt and Frankfurt | Official website identity; Instagram/Strava for occurrence details | Website explicitly warns locations may vary. Darmstadt shop address is not confirmation of the next run's meeting point. |
| [Darmstädter Lauf-Treff](https://www.darmstaedter-lauftreff.de/wann-wo-wie/) | Recurring public running/walking groups | Explicit schedule plus homepage cancellation notices | Preserve seasonal times and cancellation exceptions; don't infer training attendance size. |
| [Stiftung Hofgut Oberfeld](https://www.stiftung-oberfeld.de/aktuelles-termine.html) | Farm education, outdoor culture, exhibitions and concerts | HTML dates and programme downloads | Several meeting points on the grounds; overlaps with Initiative Domäne Oberfeld. |
| [Initiative Domäne Oberfeld](https://www.initiative-oberfeld.de/veranstaltungen.html) | Farm, nature and community programme | HTML event details and calendar downloads | Treat shared Hofgut announcements as one occurrence with multiple sources. |
| [Kinder-Jugend-Freizeiten](https://www.kinder-jugend-freizeiten.de/) | Holiday activities and youth-provider discovery | Provider directory and programme records | Darmstadt can be a departure point for a trip elsewhere; do not plot destination activities as city events. |
| [BDKJ Darmstadt](https://www.bdkj-darmstadt.de/termine) | Children, youth and community activities | HTML dated listings | Includes regional events and training for specific groups; preserve audience and location filters. |
| [KinderKulturTage Darmstadt](https://www.kikuta-darmstadt.de/) | Children's culture and family programmes | Seasonal programme and individual notices | Identify the programme year and exact dated activities; mission text is not an event. |

### Festivals, markets and larger events

| Source | Coverage | Collection route | Important limitation |
|---|---|---|---|
| [darmstadtium](https://www.darmstadtium.de/besuchen/veranstaltungskalender) | Shows, fairs, science and conferences | HTML calendar and event detail pages | Venue calendar includes restricted conferences and ceremonies; public attendance cannot be assumed. |
| [Darmstädter Heinerfest](https://www.heinerfest.de/) | City festival and many component activities | Annual programme and individual event notices | Live homepage reports 2026 completed and no next events; retain as seasonal source without inventing 2027 dates. |
| [Golden Leaves Festival](https://goldenleavesfestival.de/) | Music festival and associated organiser discovery | Current edition page and programme announcements | Live homepage already advertises 2027 while older indexed pages still show 2026; edition must be explicit. |
| [CSD Darmstadt](https://www.csd-darmstadt.de/) | Demonstration, stage programme and related community events | Current edition page, news and linked programme | Live homepage advertises 2027 alongside 2026 programme/route links. Do not attach last year's route to next year's event. |
| [Darmstadt Citymarketing](https://www.darmstadt-citymarketing.de/aktuelles.html) | Wine festival, markets and special city activities | Dated official announcements | Ignore recruitment, retail promotion and other posts without a relevant event programme. |
| [Darmstadt Tourismus Kerb directory](https://www.darmstadt-tourismus.de/messen-und-maerkte/kirchweih-veranstaltungen.html) | Neighbourhood fairs and organiser discovery | Follow organisers and social links, then verify dates | Recurring annual descriptions alone cannot supply this year's programme; separate event umbrella and component activities. |
| [OHA / Osthang](https://www.osthang.de/) | Community culture, open meetings and temporary outdoor events | Current blog, dated calendar and official social links | Recent posts discuss a new setting and venue uncertainty; historic Olbrichweg address must not be reused automatically. |



## Evidence files

- [Curated source registry](darmstadt-sources.json): 69 entries, priorities, limitations, source-linked social URLs, and observed page status.
- [Initial public-page checks](2026-09-14-source-probe.json): 66 page checks, including an alias and supporting pages.
- [Focused follow-up checks](2026-09-14-source-followups.json): eight checks, including individual events, neighbourhood event indexes, and the corrected café response; one attempted Oetinger info path returned 404 and is not recommended.
- [Additional topic checks](2026-09-14-additional-source-probe.json): seven jazz, wine, cinema, and family sources.
- [Feed checks](2026-09-14-feed-probe.json): 22 endpoint checks with exact URLs and response observations.
- [Research totals](2026-09-14-research-summary.json): machine-readable counts used above.

The files retain metadata and links rather than copies of full articles or complete event descriptions. Technical response checks establish retrieval feasibility at check time, not ongoing reliability, an implemented parser, publication permission, or complete event coverage.
