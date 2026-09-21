"""Warm the geocache for every unresolved street, then geocode to completion.

Existing collection runs cap geocoding at 20 new Nominatim lookups per run so
the map only fills slowly over weeks. This backfill resolves every street that
has not been geocoded yet, respecting the same 1.1 s politeness sleep.
"""
import json
import logging
import os
import sys
from pathlib import Path

from .collect import Collector, street_city, now_local
from .db import Database, ROOT
from .export_static import DEFAULT_OUT, collect as collect_payload
from .network import fetch

log = logging.getLogger(__name__)


def unresolved_streets(db):
    """Distinct street keys for published events lacking a resolved location."""
    seen = set()
    for event in db.events('published'):
        if event.get('lat') is not None and not str(event.get('coordinate_evidence') or '').startswith('Approximate'):
            continue
        street, city = street_city(event.get('address') or '')
        if not street:
            continue
        seen.add(street.casefold() + ', ' + city.casefold())
    return seen


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    db = Database(os.environ.get('DARMSTADT_DB'))
    collector = Collector(db, fetch=fetch, now=now_local)
    pending = unresolved_streets(db)
    limit = int(args[0]) if args else max(1, len(pending))
    try:
        collector.geocode(limit=limit)
    except Exception as exc:
        log.warning('geocoding failed: %s', exc)
    payload = collect_payload(db)
    out = Path(os.environ.get('DARMSTADT_OUT', DEFAULT_OUT))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    log.info('geocoded up to %s new streets; exported %s', limit, out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())