"""Warm the geocache for every unresolved street, then geocode to completion.

Existing collection runs cap geocoding at 20 new Nominatim lookups per run so
the map only fills slowly over weeks. This backfill resolves every street that
has not been geocoded yet, respecting the same 1.1 s politeness sleep.
"""
import json
import logging
import os
import sys

from .collect import Collector, street_address, infer_area, now_local
from .db import Database, ROOT
from .export_static import collect as collect_payload
from .network import fetch

log = logging.getLogger(__name__)


def unresolved_streets(db):
    """Distinct street keys for published events lacking a resolved location."""
    seen = set()
    for event in db.events('published'):
        if event.get('lat') is not None and not str(event.get('coordinate_evidence') or '').startswith('Approximate'):
            continue
        street = street_address(event.get('address') or '')
        if not street:
            continue
        city = infer_area(event.get('address') or '') or 'Darmstadt'
        seen.add(street.casefold() + ', ' + city.casefold())
    return seen


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    db = Database(os.environ.get('DARMSTADT_DB'))
    collector = Collector(db, fetch=fetch, now=now_local)
    pending = unresolved_streets(db)
    limit = int(args[0]) if args else max(1, len(pending))
    collector.geocode(limit=limit)
    payload = collect_payload(db)
    out = ROOT / 'web/public/data.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    log.info('geocoded up to %s new streets; exported %s', limit, out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())