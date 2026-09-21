from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.collect import parse_html_llm
import app.llm_extract as llm

from bs4 import BeautifulSoup

TZ = ZoneInfo('Europe/Berlin')
NOW = datetime(2026, 9, 20, 16, tzinfo=TZ)


def test_strip_html_removes_navigation_and_normalizes_text():
    text = llm.strip_html(
        '<html><nav>Menu Impressum</nav><p>Konzert am <b>20.10.2026</b> im Café</p>'
        '<script>var x=1;</script></html>')
    assert 'Menu' not in text
    assert 'Impressum' not in text
    assert 'Konzert am' in text
    assert 'im Café' in text


@pytest.mark.parametrize('value,expected', [
    ('2026-10-20T19:30', datetime(2026, 10, 20, 19, 30, tzinfo=TZ)),
    ('2026-10-20T19:30:00', datetime(2026, 10, 20, 19, 30, tzinfo=TZ)),
    ('20. Oktober 2026, 19:30', datetime(2026, 10, 20, 19, 30, tzinfo=TZ)),
    ('20.10.2026 19:30', datetime(2026, 10, 20, 19, 30, tzinfo=TZ)),
    ('20.5.26', datetime(2026, 5, 20, tzinfo=TZ)),
    ('', None),
    ('bald', None),
    ('2026-13-99T25:99', None),
])
def test_parse_datetime_formats(value, expected):
    assert llm._parse_datetime(value) == expected


def test_model_events_parses_fenced_json():
    payload = '```json\n{"events":[{"title":"A"},{"title":"B"}]}\n```'
    assert [e['title'] for e in llm._model_events(payload)] == ['A', 'B']


def test_model_events_rejects_non_objects_and_broken_json():
    assert llm._model_events('kein json') == []
    assert llm._model_events('{"nope":1}') == []
    assert llm._model_events('[]') == []


def test_extract_events_from_html_passes_bounded_text_and_emits_validated_events(monkeypatch):
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['url'] = url
        captured['messages'] = json['messages']
        content = json['messages'][1]['content']
        assert len(content) <= llm.MAX_TEXT_CHARS  # truncated from the padded page
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {'choices': [{'message': {'content': (
                    '{"events":[{"title":"Theaterabend","start":"2026-10-20T19:30",'
                    '"venue":"HoffART","address":"Landgraf-Georg-Straße 4, Darmstadt",'
                    '"description":"Ein Abend."}]}')}}]}
        return _Resp()

    monkeypatch.setattr(llm.httpx, 'post', fake_post)
    events = llm.extract_events_from_html('<p>' + 'Bühne und Konzerte im Herbst. ' * 30 + '</p>', 'https://x.example/', NOW)
    assert captured['url'].endswith('/chat/completions')
    assert events and events[0]['title'] == 'Theaterabend'
    assert events[0]['start'].startswith('2026-10-20T19:30')
    assert events[0]['url'] == 'https://x.example/'
    assert len(events[0]['external_id']) == 32


def test_extract_events_from_html_swallows_model_failures(monkeypatch):
    def fail_post(*args, **kwargs):
        raise RuntimeError('connection refused')

    monkeypatch.setattr(llm.httpx, 'post', fail_post)
    assert llm.extract_events_from_html(b'<p>an event</p>', 'https://x.example/', NOW) == []


def test_extract_events_from_html_skips_short_pages(monkeypatch):
    assert llm.extract_events_from_html(b'<p>hi</p>', 'https://x.example/', NOW) == []


def test_parse_html_llm_publishes_events_with_ai_badge(monkeypatch):
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured['json'] = json
        class _Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {'choices': [{'message': {'content': (
                    '{"events":[{"title":"Open Mic","start":"2026-10-15T20:00",'
                    '"end":"2026-10-15T22:00","venue":"Keller-Klub","address":"Schulstraße 6, Darmstadt",'
                    '"description":"Bühne frei."},{"title":"Ausverkauft damals","start":"2020-01-01T10:00"}]}')}}]}
        return _Resp()

    monkeypatch.setattr(llm.httpx, 'post', fake_post)
    events = parse_html_llm(b'<html><body>' + b'Open Mics und Konzerte. ' * 30 + b'</body></html>', 'hoffart', NOW, NOW + timedelta(days=90))
    assert len(events) == 1
    event = events[0]
    assert event['title'] == 'Open Mic'
    assert event['status'] == 'published'
    assert event['ai_extracted'] is True
    assert not event['review_reason']
    assert event['end'] == '2026-10-15T22:00:00+02:00'
    assert event['url']