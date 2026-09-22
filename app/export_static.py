import json
import os
import sys
from pathlib import Path

from .db import Database, ROOT

DEFAULT_OUT = ROOT / 'web/public/darmstadt/data.json'


def collect(db):
    sources = db.sources()
    events = db.events()
    return dict(events=db.events('published'), review=db.events('review'),
                sources=sources, candidates=db.candidates(),
                status=dict(running=False, last_run=db.get_meta('last_run'), next_due=db.get_meta('next_due'),
                            last_result=db.get_meta('last_result'), source_count=len(sources),
                            active_sources=sum(s['enabled'] and s['implemented'] for s in sources),
                            event_count=sum(e['status'] == 'published' for e in events),
                            review_count=sum(e['status'] == 'review' for e in events),
                            collection_progress='',
                            capabilities={'social': False, 'ocr': False, 'web_search': False}))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    out = Path(args[0]) if args else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = collect(Database(os.environ.get('DARMSTADT_DB')))
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())