from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.collect import parse_ical, parse_jsonld, parse_city_html, extract_event_image, Collector, base_event, infer_area
from app.db import Database
from app.network import validate_url
from bs4 import BeautifulSoup

TZ = ZoneInfo('Europe/Berlin')
NOW = datetime(2026, 9, 14, 12, tzinfo=TZ)


def calendar(events):
    return ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n' + events + 'END:VCALENDAR\r\n').encode()


def vevent(uid='one', start='20260914T190000', extra=''):
    return f'BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART;TZID=Europe/Berlin:{start}\r\nSUMMARY:Spieleabend\r\nLOCATION:Café, Darmstadt\r\n{extra}END:VEVENT\r\n'


def test_recurrence_exdate_override_and_dst():
    raw = calendar(vevent(extra='RRULE:FREQ=WEEKLY;COUNT=8\r\nEXDATE;TZID=Europe/Berlin:20260921T190000\r\n') + vevent(start='20260929T200000', extra='RECURRENCE-ID;TZID=Europe/Berlin:20260928T190000\r\n'))
    events = parse_ical(raw, 'nbh', NOW, NOW + timedelta(days=60))
    assert len(events) == 7
    assert not any(e['start'].startswith('2026-09-21') for e in events)
    moved = next(e for e in events if e['start'].startswith('2026-09-29'))
    assert '2026-09-28' in moved['external_id']
    assert events[-1]['start'].endswith('+01:00')
    assert events[-1]['start'][11:16] == '19:00'
    assert len({e['external_id'] for e in events}) == len(events)


def test_all_day_and_cancelled_are_not_invented_times():
    raw = calendar('BEGIN:VEVENT\r\nUID:day\r\nDTSTART;VALUE=DATE:20260915\r\nSUMMARY:Fest\r\nSTATUS:CANCELLED\r\nEND:VEVENT\r\n')
    event = parse_ical(raw, 'nbh', NOW, NOW + timedelta(days=7))[0]
    assert event['all_day'] and event['cancelled']
    assert event['scale'] == 'unknown'
    assert event['free'] is None


def test_ical_parser_keeps_attached_image_url():
    raw = calendar(vevent(extra='ATTACH:https://events.example/poster.jpg\r\n'))
    event = parse_ical(raw, 'nbh', NOW, NOW + timedelta(days=7))[0]
    assert event['image_url'] == 'https://events.example/poster.jpg'


def test_jsonld_zero_duration_and_html_are_handled():
    raw = b'<script type="application/ld+json">{"@type":"Event","name":"Quiz","startDate":"2026-09-15T20:00:00+02:00","endDate":"2026-09-15T20:00:00+02:00","description":"<b>Hello</b>","location":{"name":"KNEIPE"}}</script>'
    event = parse_jsonld(raw, 'goldene-krone', NOW, NOW + timedelta(days=7))[0]
    assert event['end'] is None
    assert event['description'] == 'Hello'
    assert 'Schustergasse 18' in event['address']


def test_event_image_prefers_jsonld_and_resolves_relative_url():
    soup = BeautifulSoup('<meta property="og:image" content="/og.jpg">', 'html.parser')
    assert extract_event_image(
        soup,
        {'image': {'url': '/events/quiz-poster.jpg'}},
        'https://events.example/calendar',
    ) == 'https://events.example/events/quiz-poster.jpg'


def test_event_image_falls_back_to_open_graph_then_relevant_img():
    soup = BeautifulSoup('''
      <meta property="og:image" content="/og-poster.jpg">
      <meta name="twitter:image" content="/twitter-poster.jpg">
      <article><img src="/event-poster.jpg" alt="Event poster"></article>
    ''', 'html.parser')
    assert extract_event_image(soup, page_url='https://events.example/calendar') == 'https://events.example/og-poster.jpg'

    no_meta = BeautifulSoup('<article><img src="/event-poster.jpg" alt="Event poster"></article>', 'html.parser')
    assert extract_event_image(no_meta, page_url='https://events.example/calendar') == 'https://events.example/event-poster.jpg'

    srcset_only = BeautifulSoup('<article><img srcset="/poster-small.jpg 400w, /poster-large.jpg 1200w" alt="Event poster"></article>', 'html.parser')
    assert extract_event_image(srcset_only, page_url='https://events.example/calendar') == 'https://events.example/poster-small.jpg'

    invalid_og = BeautifulSoup('''
      <meta property="og:image" content="http://127.0.0.1/private.png">
      <meta name="twitter:image" content="/twitter-poster.jpg">
    ''', 'html.parser')
    assert extract_event_image(invalid_og, page_url='https://events.example/calendar') == 'https://events.example/twitter-poster.jpg'


def test_event_image_rejects_unsafe_and_generic_assets():
    soup = BeautifulSoup('''
      <meta property="og:image" content="data:image/png;base64,abc">
      <img src="/assets/favicon.ico" alt="favicon">
      <img src="/assets/site-logo.svg" alt="logo">
    ''', 'html.parser')
    assert extract_event_image(soup, page_url='https://events.example/calendar') is None


def test_jsonld_parser_keeps_event_image():
    raw = b'''<script type="application/ld+json">{
      "@type":"Event", "name":"Image event", "startDate":"2026-09-15T20:00:00+02:00",
      "location":{"name":"KNEIPE"}, "image":"/images/event.jpg"
    }</script>'''
    event = parse_jsonld(raw, 'goldene-krone', NOW, NOW + timedelta(days=7))[0]
    assert event['image_url'] == 'https://www.goldene-krone.de/images/event.jpg'


def test_conflicting_title_and_calendar_addresses_require_review():
    from app.collect import base_event
    event = base_event('Umsonstladen, Bessunger Str. 132, ist geöffnet', '2026-09-14T15:00:00+02:00',
                       venue='Quartierladen', address='Quartierladen, Binger Str. 8b, Darmstadt')
    assert event['status'] == 'review'
    assert 'address' in event['review_reason']


def test_standalone_uid_survives_reschedule(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    first = parse_ical(calendar(vevent()), 'nbh', NOW, NOW + timedelta(days=4))[0]
    moved = parse_ical(calendar(vevent(start='20260916T190000')), 'nbh', NOW, NOW + timedelta(days=4))[0]
    eid = db.upsert_event(first, 'nbh', NOW.isoformat())
    assert db.upsert_event(moved, 'nbh', NOW.isoformat()) == eid
    assert len(db.events()) == 1
    assert db.event(eid)['start'].startswith('2026-09-16')


def test_dense_recurrence_rejected_before_expansion():
    raw = calendar(vevent(extra='RRULE:FREQ=SECONDLY\r\n'))
    with pytest.raises(ValueError, match='frequency'):
        parse_ical(raw, 'nbh', NOW, NOW + timedelta(days=90))


def test_topic_words_and_description_address_conflicts():
    from app.collect import infer_topics, base_event
    assert 'food' not in infer_topics('Schachforum', 'Ein Verein in Hessen')
    assert infer_topics('Sportangebot für Kinder', 'Spielerisch lernen')[0] == 'outdoors'
    event = base_event('Unser Kiosk', '2026-09-14T15:00:00+02:00', venue='Quartierladen',
                       address='Binger Str. 8b, Darmstadt', description='Besuchen Sie uns: Moltkestraße 1A, 64295 Darmstadt')
    assert event['status'] == 'review'


def test_end_across_fall_back_is_compared_as_an_instant():
    from app.collect import base_event
    event = base_event('Night concert', '2026-10-25T02:30:00+02:00', venue='Darmstadt', end='2026-10-25T02:15:00+01:00')
    assert event['end'] == '2026-10-25T02:15:00+01:00'


@pytest.mark.parametrize('description,free', [('Kosten: frei', True), ('Kosten: 5 €', False), ('Kostenloser Parkplatz am kostenpflichtigen Konzert', None)])
def test_only_explicit_event_prices_classify_free_admission(description, free):
    event = parse_ical(calendar(vevent(extra='DESCRIPTION:' + description + '\r\n')), 'nbh', NOW, NOW + timedelta(days=2))[0]
    assert event['free'] is free


def test_dedup_provenance_distinct_performances_and_review_survives(tmp_path):
    db = Database(tmp_path / 'test.sqlite')
    event = parse_ical(calendar(vevent()), 'nbh', NOW, NOW + timedelta(days=2))[0]
    first = db.upsert_event(event, 'nbh', NOW.isoformat())
    other = dict(event, external_id='mirror')
    assert db.upsert_event(other, 'lincoln', NOW.isoformat()) == first
    assert len(db.event(first)['provenance']) == 2
    db.edit_event(first, {'title': 'Reviewed title', 'scale': 'small', 'scale_evidence': 'Organiser confirmed intimate group', 'status': 'published'})
    db.upsert_event(event, 'nbh', (NOW + timedelta(days=1)).isoformat())
    assert db.event(first)['title'] == 'Reviewed title'
    assert db.event(first)['scale'] == 'small'
    late = dict(event, external_id='late', start='2026-09-14T21:00:00+02:00')
    assert db.upsert_event(late, 'nbh', NOW.isoformat()) != first
    assert Database(tmp_path / 'test.sqlite').event(first)['scale'] == 'small'


def test_failed_fetch_preserves_data_and_records_error(tmp_path):
    db = Database(tmp_path / 'test.sqlite')
    event = parse_ical(calendar(vevent()), 'nbh', NOW, NOW + timedelta(days=2))[0]
    event_id = db.upsert_event(event, 'nbh', NOW.isoformat())
    def broken(url):
        raise RuntimeError('upstream unavailable')
    collector = Collector(db, fetch=broken, now=lambda: NOW)
    collector.run(source_ids=['nbh'], discover=False, geocode=False)
    assert db.event(event_id)['last_checked'] == NOW.isoformat()
    assert not db.event(event_id)['cancelled']
    assert 'upstream unavailable' in next(s for s in db.sources() if s['id'] == 'nbh')['error']


def test_persistent_due_and_nonoverlap(tmp_path):
    db = Database(tmp_path / 'test.sqlite')
    c = Collector(db, now=lambda: NOW)
    assert not c.due()  # first collection is explicit
    db.set_meta('next_due', (NOW - timedelta(days=30)).isoformat())
    assert c.due()
    c.lock.acquire()
    assert c.run(source_ids=[], discover=False, geocode=False) is False
    c.lock.release()
    assert c.run(source_ids=[], discover=False, geocode=False) is True
    assert not Collector(Database(tmp_path / 'test.sqlite'), now=lambda: NOW).due()
    assert datetime.fromisoformat(db.get_meta('next_due')) == NOW + timedelta(days=7)


@pytest.mark.parametrize('url', ['http://localhost/test', 'http://127.0.0.1', 'http://169.254.169.254', 'file:///etc/passwd', 'http://user:pass@example.com', 'http://[::1]', 'https://example.com:8443'])
def test_private_or_unsupported_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_supported_neighbouring_municipalities_are_local():
    assert infer_area('Rathausplatz 1, 64347 Griesheim') == 'Griesheim'
    assert infer_area('Hauptstraße 1, 64331 Weiterstadt') == 'Weiterstadt'
    event = base_event('Stadtfest', '2026-09-20T10:00:00+02:00', venue='Marktplatz', address='64347 Griesheim')
    assert event['status'] == 'published'
    assert event['area'] == 'Griesheim'


def test_source_directory_includes_neighbouring_and_spielmobil_sources(tmp_path):
    ids = {source['id'] for source in Database(tmp_path / 'sources.sqlite').sources()}
    assert {'griesheim-city', 'weiterstadt-city', 'spielmobil-darmstadt'} <= ids


def test_griesheim_html_occurrence_parser_keeps_city_and_dates():
    raw = '''<div class="calendar">
      <div class="row mb-5"><h2><a href="/veranstaltungen/event/termin/spielmobil-20260920">Das Rotzfreche Spielmobil</a></h2>
      <h4>20.09.2026 15:00 - 19:00</h4><img src="/media/spielmobil.jpg" alt="Spielmobil poster"><p>Freies Spielangebot für Kinder</p></div>
    </div>'''.encode()
    events = parse_city_html(raw, 'griesheim-city', NOW, NOW + timedelta(days=30))
    assert len(events) == 1
    assert events[0]['area'] == 'Griesheim'
    assert events[0]['lat'] is not None and events[0]['lon'] is not None
    assert events[0]['coordinate_evidence'].startswith('Approximate')
    assert events[0]['image_url'] == 'https://www.griesheim.de/media/spielmobil.jpg'
    assert events[0]['start'].startswith('2026-09-20T15:00')


def test_weiterstadt_html_parser_preserves_multiday_end():
    raw = '''<div class="panel-group" id="accordion-2026-1"><div class="panel">
      <div class="panel-heading"><span class="date">Fr 02.10. – 05.10.26</span><span class="event-title">Grewweheiser Kerb</span></div>
      <div class="panel-body event-container"><label>Beginn:</label> 18:00 Uhr<br /><label>Ende:</label> 23:00 Uhr<br /><label>Ort:</label> Bürgerhaus Weiterstadt<br /><label>Veranstalter:</label> Stadt Weiterstadt<hr><p>Vier Tage Festbetrieb.</p></div>
    </div></div>'''.encode()
    events = parse_city_html(raw, 'weiterstadt-city', NOW, NOW + timedelta(days=40))
    assert len(events) == 1
    assert events[0]['area'] == 'Weiterstadt'
    assert events[0]['lat'] is not None and events[0]['lon'] is not None
    assert events[0]['coordinate_evidence'].startswith('Approximate')
    assert events[0]['start'].startswith('2026-10-02T18:00')
    assert events[0]['end'].startswith('2026-10-05T23:00')
