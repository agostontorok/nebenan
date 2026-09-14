"""Verified endpoints and the small set of post-discovery local additions."""

COLLECTORS = {
    'nbh': ('ical', 'https://nbh-darmstadt.de/veranstaltungen/?ical=1'),
    'eberstadt': ('ical', 'https://www.eberstaedter-buergerverein.de/veranstaltungen/liste/?ical=1'),
    'lincoln': ('ical', 'https://www.lincoln-darmstadt.de/events/?ical=1'),
    'postsiedlung': ('ical', 'https://www.postsiedlung.de/events/?ical=1'),
    'jazzinstitut': ('ical', 'https://www.jazzinstitut.de/jazzkalender/?ical=1'),
    'vielbunt': ('ical', 'https://calendar.google.com/calendar/ical/vielbunt.org_9dumkl9hgmdsf22bvi3vb7du78%40group.calendar.google.com/public/basic.ics'),
    'transition': ('ical', 'https://transition-darmstadt.de/?plugin=all-in-one-event-calendar&controller=ai1ec_exporter_controller&action=export_events&no_html=true&ai1ec_cat_ids=53,52,19,13,23,73,22,17,57,20,15,16,14,25'),
    'frizz': ('ical', 'https://www.frizzmag.de/search/event/veranstaltungs-kalender/calendar.ics'),
    'goldene-krone': ('jsonld', 'https://www.goldene-krone.de/'),
    'griesheim-city': ('griesheim-html', 'https://www.griesheim.de/veranstaltungen'),
    'weiterstadt-city': ('weiterstadt-html', 'https://www.weiterstadt.de/verwaltung-service/aktuelles/termine-veranstaltungen/index.php?y=2026'),
}

# These municipal and special-programme sources were added after the initial
# discovery pass.  The Spielmobil publishes route information and posters,
# rather than a stable feed, so it stays a researched/manual source for now.
EXTRA_SOURCES = [
    {
        'id': 'spielmobil-darmstadt',
        'name': 'Das Rotzfreche SPIELMOBIL · SJD Die Falken',
        'url': 'https://spielmobil-darmstadt.de/spielmobil/',
        'additional_pages': ['https://www.darmstadt.de/leben/soziales/kinder-und-jugendliche/kinder-und-jugendhaeuser'],
        'category': 'Family and youth',
        'role': 'organiser',
        'integration_priority': 1,
        'coverage': 'Free mobile play programme in Darmstadt neighbourhoods, April–October',
        'recommended_collection': 'Route schedule review and manual poster intake',
        'limitations': 'The route is announced on the website, posters and social media; no stable calendar feed was found.',
        'checked_on': '2026-09-14',
        'page_status': 'retrieved',
        'observed_http_status': 200,
        'observed_page_title': 'Spielmobil Darmstadt',
        'observed_event_jsonld_count': 0,
        'linked_social_profiles': [{'url': 'https://www.instagram.com/spielmobile_in_darmstadt/', 'evidence_url': 'https://www.darmstadt.de/leben/soziales/kinder-und-jugendliche/kinder-und-jugendhaeuser', 'verification': 'linked by the city page'}],
        'observed_feed_links': [],
        'automation_status': 'researched_not_implemented',
    },
    {
        'id': 'griesheim-city',
        'name': 'Stadt Griesheim Veranstaltungskalender',
        'url': 'https://www.griesheim.de/veranstaltungen',
        'additional_pages': [],
        'category': 'Neighbouring municipalities',
        'role': 'city_calendar',
        'integration_priority': 1,
        'coverage': 'Public programmes and recurring activities in Griesheim',
        'recommended_collection': 'HTML occurrence pages',
        'limitations': 'The list gives dates and summaries; exact venue details are not present in every list entry.',
        'checked_on': '2026-09-14',
        'page_status': 'retrieved',
        'observed_http_status': 200,
        'observed_page_title': 'Veranstaltungen · Stadt Griesheim',
        'observed_event_jsonld_count': 0,
        'linked_social_profiles': [],
        'observed_feed_links': [],
        'automation_status': 'implemented',
    },
    {
        'id': 'weiterstadt-city',
        'name': 'Stadt Weiterstadt Termine & Veranstaltungen',
        'url': 'https://www.weiterstadt.de/verwaltung-service/aktuelles/termine-veranstaltungen/index.php?y=2026',
        'additional_pages': [],
        'category': 'Neighbouring municipalities',
        'role': 'city_calendar',
        'integration_priority': 1,
        'coverage': 'Public programmes, clubs and festivals in Weiterstadt and its districts',
        'recommended_collection': 'HTML accordion entries',
        'limitations': 'The year is part of the page URL; the collector follows the configured current-year page.',
        'checked_on': '2026-09-14',
        'page_status': 'retrieved',
        'observed_http_status': 200,
        'observed_page_title': 'Termine & Veranstaltungen · Stadt Weiterstadt',
        'observed_event_jsonld_count': 0,
        'linked_social_profiles': [],
        'observed_feed_links': [],
        'automation_status': 'implemented',
    },
]

TOPICS = ['music', 'culture', 'food', 'social', 'outdoors', 'family', 'learning', 'civic']
SCALES = ['unknown', 'small', 'medium', 'large', 'citywide']

SUPPORTED_PLACES = {
    'Darmstadt': {
        'aliases': ('darmstadt',),
        'postal_prefixes': ('642',),
    },
    'Griesheim': {
        'aliases': ('griesheim',),
        'postal_prefixes': ('64347',),
    },
    'Weiterstadt': {
        'aliases': ('weiterstadt', 'braunshardt', 'gräfenhausen', 'graefenhausen', 'schneppenhausen', 'riedbahn'),
        'postal_prefixes': ('64331',),
    },
}

# Municipality centres are deliberately approximate. They make nearby events
# discoverable on the map until an exact street address is confirmed.
AREA_CENTROIDS = {
    'Griesheim': (49.8615899, 8.5762043),
    'Weiterstadt': (49.9178, 8.5924),
}

# Fixed venue of this venue's own programme. No coordinates inferred from its organiser.
KRONE_ADDRESS = 'Schustergasse 18, 64283 Darmstadt'
