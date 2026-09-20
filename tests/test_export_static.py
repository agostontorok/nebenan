import json

from fastapi.testclient import TestClient

from app.db import Database
from app.export_static import main
from app.main import create_app


def build_db(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    db.upsert_event(source_event(), 'manual', '2026-09-14T10:00:00+02:00')
    db.upsert_event(source_event('two', status='review'), 'second', '2026-09-14T10:01:00+02:00')
    db.set_meta('last_run', '2026-09-14T10:00:00+02:00')
    db.set_meta('next_due', '2026-09-21T10:00:00+02:00')
    db.set_meta('last_result', {'successes': 1, 'failures': 0, 'imported': 2,
                                'started_at': '2026-09-14T10:00:00+02:00',
                                'finished_at': '2026-09-14T10:01:00+02:00'})
    return db


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


def export_to(db, out, monkeypatch):
    monkeypatch.setenv('DARMSTADT_DB', str(db.path))
    assert main([str(out)]) == 0
    return json.loads(out.read_text(encoding='utf-8'))


def test_export_writes_file_with_four_top_level_keys(tmp_path, monkeypatch):
    db = build_db(tmp_path)
    out = tmp_path / 'web' / 'public' / 'data.json'
    data = export_to(db, out, monkeypatch)
    assert set(data) == {'events', 'review', 'sources', 'candidates', 'status'}


def test_export_events_and_review_match_db(tmp_path, monkeypatch):
    db = build_db(tmp_path)
    data = export_to(db, tmp_path / 'data.json', monkeypatch)
    assert data['events'] == db.events('published')
    assert all(e['status'] == 'published' for e in data['events'])
    assert all('id' in e and 'provenance' in e for e in data['events'])
    assert data['review'] == db.events('review')
    assert all(e['status'] == 'review' for e in data['review'])


def test_export_status_matches_api_status_route(tmp_path, monkeypatch):
    db = build_db(tmp_path)
    with TestClient(create_app(db, scheduling=False)) as client:
        expected = client.get('/api/status').json()
    data = export_to(db, tmp_path / 'data.json', monkeypatch)
    assert data['status'] == expected
    assert data['status']['running'] is False


def test_export_is_deterministic(tmp_path, monkeypatch):
    db = build_db(tmp_path)
    monkeypatch.setenv('DARMSTADT_DB', str(db.path))
    out = tmp_path / 'data.json'
    main([str(out)])
    first = out.read_bytes()
    main([str(out)])
    assert out.read_bytes() == first