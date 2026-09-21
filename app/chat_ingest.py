"""Ingest events extracted manually (by chat review) from source pages.

Used in place of the local-model pipeline: a human/agent reads a source page
and records the events they can confirm. Each event is published with the
AI-extracted badge and a link back to the original page.
"""
import hashlib
import json
import sys
from datetime import datetime, timedelta

from .collect import base_event, now_local
from .db import Database


def _event_id(source, page_url, title, start):
    return hashlib.sha256(f'{source}|{page_url}|{title}|{start}'.encode()).hexdigest()[:32]


def ingest(db, entries):
    checked = now_local().isoformat()
    created, updated = 0, 0
    for entry in entries or []:
        source = entry['source']
        page_url = entry.get('page_url', '') or ''
        for item in entry.get('events', []):
            title = str(item.get('title') or '').strip()
            start = item.get('start')
            if not title or not start:
                continue
            event = base_event(
                title, start, venue=item.get('venue') or '', address=item.get('address') or '',
                description=item.get('description') or '', end=item.get('end'))
            event.update(
                status='published', ai_extracted=True, review_reason='',
                external_id=_event_id(source, page_url, title, start),
                url=item.get('url') or page_url)
            previous = ref_id(db, source, event['external_id'])
            db.upsert_event(event, source, checked)
            if previous is None:
                created += 1
            else:
                updated += 1
    return created, updated


def ref_id(db, source, external_id):
    with db.connect() as con:
        row = con.execute('SELECT event_id FROM refs WHERE source_id=? AND external_id=?',
                          (source, external_id)).fetchone()
    return row['event_id'] if row else None


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print('usage: python -m app.chat_ingest events.json [source_filter...]', file=sys.stderr)
        return 2
    path = args[0]
    filters = args[1:]
    db = Database()
    entries = json.loads(open(path, encoding='utf-8').read())
    if filters:
        entries = [e for e in entries if e['source'] in filters]
    created, updated = ingest(db, entries)
    print(f'created={created} updated={updated}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())