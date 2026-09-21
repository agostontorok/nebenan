import json

import pytest

from app.chat_ingest import ingest, ref_id, _event_id
from app.db import Database


@pytest.fixture
def tmpdb(tmp_path):
    return Database(tmp_path / 'events.sqlite')


def test_ingest_publishes_ai_badged_events(tmpdb):
    created, updated = ingest(tmpdb, [{
        'source': '806qm',
        'page_url': 'https://www.806qm.de/programm/',
        'events': [{
            'title': 'Perform & Connect',
            'start': '2026-11-06T20:00',
            'venue': '806 qm',
            'address': 'Kasinostraße 3, 64293 Darmstadt',
            'description': 'Labor für Kunst.',
            'url': 'https://www.806qm.de/programm/',
        }],
    }])
    assert created == 1
    assert updated == 0
    eid = ref_id(tmpdb, '806qm', _event_id('806qm', 'https://www.806qm.de/programm/', 'Perform & Connect', '2026-11-06T20:00'))
    assert eid
    event = tmpdb.event(eid)
    assert event['status'] == 'published'
    assert event['ai_extracted'] is True
    assert event['title'] == 'Perform & Connect'
    assert event['provenance'][0]['source_id'] == '806qm'
    assert event['provenance'][0]['url'] == 'https://www.806qm.de/programm/'
    assert event['start'].startswith('2026-11-06T20:00')


def test_ingest_is_idempotent(tmpdb):
    entry = [{
        'source': 'keller-klub',
        'page_url': 'https://www.kellerklub-oberwaldhaus.de/',
        'events': [{
            'title': 'Kneipenkonzert',
            'start': '2026-10-02T20:00',
            'venue': 'Keller-Klub',
            'address': 'Schulstraße 6, 64283 Darmstadt',
        }],
    }]
    assert ingest(tmpdb, entry) == (1, 0)
    assert ingest(tmpdb, entry) == (0, 1)
    eid = ref_id(tmpdb, 'keller-klub', _event_id('keller-klub', 'https://www.kellerklub-oberwaldhaus.de/', 'Kneipenkonzert', '2026-10-02T20:00'))
    assert len([e for e in tmpdb.events('published') if e['id'] == eid]) == 1


def test_ingest_skips_events_without_title_or_start(tmpdb):
    assert ingest(tmpdb, [{
        'source': 'ccc',
        'page_url': 'https://www.ccc-da.de/',
        'events': [{}, {'title': 'No date'}],
    }]) == (0, 0)