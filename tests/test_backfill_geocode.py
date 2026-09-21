import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.backfill_geocode import main, unresolved_streets
from app.db import Database

TZ = ZoneInfo('Europe/Berlin')
NOW = datetime(2026, 9, 14, 12, tzinfo=TZ)


def _published_event(eid, address):
    return {
        'external_id': str(eid),
        'url': f'https://example.com/event/{eid}',
        'id': eid,
        'title': 'Kurs',
        'start': '2026-09-14T12:00:00+02:00',
        'venue': f'Volkshochschule {eid}',
        'address': address,
        'description': '',
        'topics': [],
        'scale': 'small',
        'free': None,
        'lat': None,
        'lon': None,
        'status': 'published',
        'area': 'Darmstadt',
    }


def test_unresolved_streets_skips_located_and_matches_street_pattern(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    db.upsert_event(_published_event(1, 'Schöfferstraße 3, 64285 Darmstadt'), 'nbh', NOW.isoformat())
    db.upsert_event(_published_event(2, 'Rathaus, Marktplatz'), 'nbh', NOW.isoformat())
    db.upsert_event(
        {**_published_event(3, 'Oberstraße 20, Darmstadt'), 'lat': 49.87, 'lon': 8.65,
         'coordinate_evidence': 'https://nominatim.openstreetmap.org/search?...'},
        'nbh', NOW.isoformat())
    streets = unresolved_streets(db)
    assert 'schöfferstrasse 3, darmstadt' in streets
    assert not any(s.startswith('marktplatz') for s in streets)
    assert not any(s.startswith('oberstrasse') for s in streets)


def test_backfill_loop_stops_when_all_resolved(tmp_path, monkeypatch):
    db_path = tmp_path / 'events.sqlite'
    out_path = tmp_path / 'data.json'
    monkeypatch.setenv('DARMSTADT_DB', str(db_path))
    monkeypatch.setenv('DARMSTADT_OUT', str(out_path))
    db = Database(db_path)
    db.upsert_event(_published_event(1, 'Schöfferstraße 3, 64285 Darmstadt'), 'nbh', NOW.isoformat())
    hits = []
    def fetch(url):
        hits.append(url)
        return '[{"lat": "49.872", "lon": "8.651", "display_name": "Schöfferstraße 3, Darmstadt", "address": {"house_number": "3"}}]'.encode()
    monkeypatch.setattr('app.backfill_geocode.fetch', fetch)
    assert main(['10']) == 0
    assert len(hits) == 1
    event = db.events('published')[0]
    assert event['lat'] == pytest.approx(49.872, abs=0.001)
    assert event['lon'] == pytest.approx(8.651, abs=0.001)
    assert event['coordinate_evidence'].startswith('https://nominatim')
    exported = json.loads(out_path.read_text())
    assert any(e['id'] == event['id'] for e in exported['events'])


def test_backfill_export_still_written_on_fetch_failure(tmp_path, monkeypatch):
    db_path = tmp_path / 'events.sqlite'
    out_path = tmp_path / 'data.json'
    monkeypatch.setenv('DARMSTADT_DB', str(db_path))
    monkeypatch.setenv('DARMSTADT_OUT', str(out_path))
    db = Database(db_path)
    db.upsert_event(_published_event(1, 'Schöfferstraße 3, 64285 Darmstadt'), 'nbh', NOW.isoformat())
    def fetch(url):
        raise RuntimeError('Nominatim down')
    monkeypatch.setattr('app.backfill_geocode.fetch', fetch)
    assert main(['10']) == 0
    event = db.events('published')[0]
    exported = json.loads(out_path.read_text())
    assert any(e['id'] == event['id'] for e in exported['events'])
