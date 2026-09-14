from app.db import Database


def source_event(external_id='one', **changes):
    event = {
        'external_id': external_id,
        'url': 'https://example.com/event',
        'title': 'Community night',
        'start': '2026-09-20T19:00:00+02:00',
        'end': '2026-09-20T21:00:00+02:00',
        'all_day': False,
        'venue': 'Community hall',
        'address': 'Main Street 1, Darmstadt',
        'description': '',
        'topics': ['social'],
        'scale': 'unknown',
        'scale_evidence': '',
        'price': None,
        'free': None,
        'lat': None,
        'lon': None,
        'coordinate_evidence': None,
        'status': 'published',
        'cancelled': False,
        'review_reason': '',
    }
    event.update(changes)
    return event


def test_source_disagreement_is_preserved_and_changed_facts_reopen_review(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    eid = db.upsert_event(source_event(), 'first', '2026-09-14T10:00:00+02:00')
    conflicting = source_event('mirror', address='Other Street 2, Darmstadt')
    assert db.upsert_event(conflicting, 'second', '2026-09-14T10:01:00+02:00') == eid

    event = db.event(eid)
    assert event['status'] == 'review'
    assert event['address'] == 'Main Street 1, Darmstadt'
    assert 'address' in event['review_reason']
    snapshots = {record['source_id']: record['snapshot'] for record in event['provenance']}
    assert snapshots['first']['address'] == 'Main Street 1, Darmstadt'
    assert snapshots['second']['address'] == 'Other Street 2, Darmstadt'

    db.edit_event(eid, {'status': 'published', 'review_reason': ''})
    db.upsert_event(conflicting, 'second', '2026-09-15T10:00:00+02:00')
    assert db.event(eid)['status'] == 'published'

    changed = source_event(
        'mirror',
        start='2026-09-20T20:00:00+02:00',
        end='2026-09-20T23:00:00+02:00',
        address='Other Street 2, Darmstadt',
        cancelled=True,
    )
    db.upsert_event(changed, 'second', '2026-09-16T10:00:00+02:00')
    event = db.event(eid)
    assert event['status'] == 'review'
    assert event['start'] == '2026-09-20T19:00:00+02:00'
    assert event['end'] == '2026-09-20T21:00:00+02:00'
    assert event['cancelled'] is False
    assert 'start' in event['review_reason']
    assert 'end' in event['review_reason']
    assert 'cancelled' in event['review_reason']


def test_single_source_material_updates_apply_without_losing_reviewed_edits(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    eid = db.upsert_event(source_event(), 'first', '2026-09-14T10:00:00+02:00')
    db.edit_event(eid, {
        'title': 'Reviewed community night',
        'scale': 'small',
        'scale_evidence': 'Reviewed by organiser',
    })

    db.upsert_event(source_event(
        start='2026-09-20T20:00:00+02:00',
        end='2026-09-20T22:00:00+02:00',
        cancelled=True,
    ), 'first', '2026-09-15T10:00:00+02:00')

    event = db.event(eid)
    assert event['start'] == '2026-09-20T20:00:00+02:00'
    assert event['end'] == '2026-09-20T22:00:00+02:00'
    assert event['cancelled'] is True
    assert event['title'] == 'Reviewed community night'
    assert event['scale'] == 'small'


def test_approved_event_reopens_when_changed_source_location_needs_review(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    eid = db.upsert_event(source_event(), 'first', '2026-09-14T10:00:00+02:00')
    db.edit_event(eid, {'status': 'published', 'review_reason': ''})

    unresolved = source_event(
        venue='Location to be announced',
        address='',
        status='review',
        review_reason='Darmstadt event location needs confirmation',
    )
    db.upsert_event(unresolved, 'first', '2026-09-15T10:00:00+02:00')

    event = db.event(eid)
    assert event['status'] == 'review'
    assert event['review_reason'] == 'Darmstadt event location needs confirmation'


def test_approved_event_reopens_when_source_title_disappears(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    eid = db.upsert_event(source_event(), 'first', '2026-09-14T10:00:00+02:00')
    db.edit_event(eid, {
        'title': 'Reviewed community night',
        'status': 'published',
        'review_reason': '',
    })

    missing_title = source_event(
        title='',
        status='review',
        review_reason='Missing title',
    )
    db.upsert_event(missing_title, 'first', '2026-09-15T10:00:00+02:00')

    event = db.event(eid)
    assert event['title'] == 'Reviewed community night'
    assert event['status'] == 'review'
    assert event['review_reason'] == 'Missing title'


def test_missing_price_flags_do_not_carry_into_changed_source_record(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    eid = db.upsert_event(
        source_event(price='Free admission', free=True),
        'first',
        '2026-09-14T10:00:00+02:00',
    )

    db.upsert_event(
        source_event(price='5 €', free=None),
        'first',
        '2026-09-15T10:00:00+02:00',
    )

    event = db.event(eid)
    assert event['price'] == '5 €'
    assert event['free'] is None


def test_approved_event_reopens_for_description_derived_source_review(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    eid = db.upsert_event(source_event(), 'first', '2026-09-14T10:00:00+02:00')
    db.edit_event(eid, {'status': 'published', 'review_reason': ''})

    changed = source_event(
        description='Announcement now contains conflicting location details',
        status='review',
        review_reason='Description and calendar address conflict',
    )
    db.upsert_event(changed, 'first', '2026-09-15T10:00:00+02:00')

    event = db.event(eid)
    assert event['status'] == 'review'
    assert event['review_reason'] == 'Description and calendar address conflict'


def test_coordinates_follow_only_an_unchanged_source_location(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    located = source_event(lat=49.87, lon=8.65, coordinate_evidence='source GEO')
    eid = db.upsert_event(located, 'first', '2026-09-14T10:00:00+02:00')

    db.upsert_event(source_event(description='Updated'), 'first', '2026-09-15T10:00:00+02:00')
    assert db.event(eid)['lat'] == 49.87

    db.edit_event(eid, {'lat': 49.88, 'lon': 8.66})
    moved = source_event(venue='New hall', address='New Street 3, Darmstadt')
    db.upsert_event(moved, 'first', '2026-09-16T10:00:00+02:00')
    event = db.event(eid)
    assert event['lat'] is None
    assert event['lon'] is None
    assert event['coordinate_evidence'] is None

    db.edit_event(eid, {
        'venue': 'Reviewed location',
        'address': 'Reviewed Street 4, Darmstadt',
        'lat': 49.89,
        'lon': 8.67,
    })
    db.upsert_event(source_event(venue='Third hall', address='Third Street 5, Darmstadt'),
                    'first', '2026-09-17T10:00:00+02:00')
    event = db.event(eid)
    assert event['lat'] == 49.89
    assert event['lon'] == 8.67


def test_manual_location_change_clears_source_coordinates_until_replaced(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    located = source_event(lat=49.87, lon=8.65, coordinate_evidence='source GEO')
    eid = db.upsert_event(located, 'first', '2026-09-14T10:00:00+02:00')

    db.edit_event(eid, {'address': 'Reviewed Street 4, Darmstadt'})
    event = db.event(eid)
    assert event['lat'] is None
    assert event['lon'] is None
    assert event['coordinate_evidence'] is None

    db.upsert_event(located, 'first', '2026-09-15T10:00:00+02:00')
    event = db.event(eid)
    assert event['address'] == 'Reviewed Street 4, Darmstadt'
    assert event['lat'] is None
    assert event['lon'] is None


def test_events_loads_sources_and_provenance_in_one_connection(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    db.upsert_event(source_event('one'), 'first', '2026-09-14T10:00:00+02:00')
    db.upsert_event(source_event('two', title='Other night'), 'second', '2026-09-14T10:00:00+02:00')
    original_connect = db.connect
    calls = 0

    def counted_connect():
        nonlocal calls
        calls += 1
        return original_connect()

    db.connect = counted_connect
    assert len(db.events()) == 2
    assert calls == 1


def test_standalone_calendar_uid_replaces_legacy_uid_date_reference(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    event = source_event('calendar-uid|2026-09-20T19:00:00+02:00')
    eid = db.upsert_event(event, 'first', '2026-09-14T10:00:00+02:00')

    rescheduled = source_event('calendar-uid', start='2026-09-21T20:00:00+02:00')
    assert db.upsert_event(rescheduled, 'first', '2026-09-15T10:00:00+02:00') == eid
    provenance = db.event(eid)['provenance']
    assert [(record['source_id'], record['external_id']) for record in provenance] == [
        ('first', 'calendar-uid')
    ]
