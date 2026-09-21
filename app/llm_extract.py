"""LLM-assisted event extraction from human-readable website pages.

Runs against a local OpenAI-compatible endpoint (Ollama by default). The
model must answer with a strict JSON list of events; anything that does not
conform is dropped, never published. Extraction is bounded and defensive:
text is truncated, the request has a hard timeout, and every failure returns
no or only validated events so a collection run is never taken down.
"""
import hashlib
import json
import logging
import os
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger(__name__)
TZ = ZoneInfo('Europe/Berlin')

OLLAMA_URL = os.environ.get('DARMSTADT_OLLAMA_URL', 'http://127.0.0.1:11434/v1')
OLLAMA_MODEL = os.environ.get('DARMSTADT_OLLAMA_MODEL', 'gpt-oss:20b-cloud')
OLLAMA_TIMEOUT = float(os.environ.get('DARMSTADT_OLLAMA_TIMEOUT', '180'))
MAX_TEXT_CHARS = 60000

SYSTEM_PROMPT = (
    'You extract local community events in and around Darmstadt, Germany from website content. '
    'Answer with ONLY a JSON object on a single line with the shape '
    '{"events":[{"title":string,"start":"YYYY-MM-DDTHH:MM","end":"YYYY-MM-DDTHH:MM"or"","venue":string,'
    '"address":string,"description":string}]}. Start and end are LOCAL Berlin wall-clock times; '
    'AM/PM is not used. Empty string for end when the event is open ended. '
    'If no event with a concrete start date can be found, return {"events":[]}. '
    'Do not invent dates, do not include news, general announcements or navigation text.'
)
USER_TEMPLATE = (
    'Today is {today} (Berlin time). '
    'Extract all events with a concrete start date that appear in the content below. '
    'Keep titles and location names exactly as written. Descriptions in at most 140 characters.\n\n'
    '{content}'
)

# Covers e.g. "10. Mai 2026, 19:30" and "10.5.2026 19:30" (German wall clock).
GERMAN_MONTHS = {'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3, 'april': 4, 'mai': 5, 'juni': 6,
                 'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12}


def strip_html(raw):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw, 'html.parser')
    for node in soup(['script', 'style', 'noscript', 'nav', 'header', 'footer', 'svg', 'form']):
        node.decompose()
    text = soup.get_text(' ', strip=True)
    return re.sub(r'\s+', ' ', text)[:MAX_TEXT_CHARS]


def _parse_datetime(value):
    """Parse an extracted start/end into a Berlin-aware datetime, or None."""
    value = re.sub(r'\s+', ' ', str(value or '').strip())
    if not value:
        return None
    iso_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})', value)
    if iso_match:
        try:
            return datetime(*map(int, iso_match.groups()), tzinfo=TZ)
        except ValueError:
            return None
    german = re.match(r'^(\d{1,2})\.\s*([A-Za-zäöüß]+)\.?\s+(\d{4})(?:,?\s+(\d{1,2}):(\d{2}))?', value)
    if german:
        day, month_name, year, hour, minute = german.groups()
        month = GERMAN_MONTHS.get(month_name.casefold())
        if month:
            try:
                return datetime(int(year), month, int(day), int(hour or 0), int(minute or 0), tzinfo=TZ)
            except ValueError:
                return None
    dotted = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?:,?\s+(\d{1,2}):(\d{2}))?', value)
    if dotted:
        day, month, year, hour, minute = dotted.groups()
        year = int(year) + 2000 if len(year) == 2 else int(year)
        try:
            return datetime(year, int(month), int(day), int(hour or 0), int(minute or 0), tzinfo=TZ)
        except ValueError:
            return None
    return None


def _model_events(payload):
    """Extract the event objects from whatever JSON the model produced."""
    text = str(payload).strip()
    fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start = text.find('{')
        end = text.rfind('}')
        if 0 <= start < end:
            text = text[start:end + 1]
        else:
            return []
    try:
        data = json.loads(text)
    except ValueError:
        data = {}
    events = data.get('events') if isinstance(data, dict) else data
    return events if isinstance(events, list) else []


def extract_events_from_html(raw, page_url, now):
    """Return validated events from one page, through the local model.

    Never raises on upstream noise: a failure logs and yields nothing. Event
    shape matches the collector's provenience ('url', 'external_id' carry the
    stable page identity; the caller merges on title+start+venue).
    """
    content = strip_html(raw)
    if len(content) < 40:
        return []
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': USER_TEMPLATE.format(today=now.strftime('%d.%m.%Y'), content=content)},
    ]
    try:
        response = httpx.post(
            OLLAMA_URL.rstrip('/') + '/chat/completions',
            json={'model': OLLAMA_MODEL, 'messages': messages, 'temperature': 0, 'stream': False},
            timeout=OLLAMA_TIMEOUT, headers={'Content-Type': 'application/json'})
        response.raise_for_status()
        payload = response.json()['choices'][0]['message']['content']
    except Exception as exc:
        log.warning('llm extraction failed for %s: %s', page_url, exc)
        return []
    events = []
    for item in _model_events(payload):
        title = re.sub(r'\s+', ' ', str(item.get('title') or '')).strip()
        start = _parse_datetime(item.get('start'))
        if not title or not start:
            continue
        end = _parse_datetime(item.get('end')) if item.get('end') else None
        if end and end <= start:
            end = None
        external_id = hashlib.sha256(f'{page_url}|{title}|{start.isoformat()}'.encode()).hexdigest()[:32]
        events.append({
            'title': title[:200],
            'start': start.isoformat(),
            'end': end.isoformat() if end else None,
            'venue': re.sub(r'\s+', ' ', str(item.get('venue') or '')).strip()[:300],
            'address': re.sub(r'\s+', ' ', str(item.get('address') or '')).strip()[:500],
            'description': re.sub(r'\s+', ' ', str(item.get('description') or '')).strip()[:1200],
            'url': page_url,
            'external_id': external_id,
        })
    return events