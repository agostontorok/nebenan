import hashlib
import json
import re
import sqlite3
import threading
from pathlib import Path

from .sources import COLLECTORS, EXTRA_SOURCES

ROOT = Path(__file__).resolve().parent.parent
MATERIAL_FIELDS = ('start', 'end', 'venue', 'address', 'cancelled')
LOCATION_FIELDS = ('venue', 'address')
APPROVAL_FIELDS = MATERIAL_FIELDS + ('title', 'description', 'status', 'review_reason')


def normalized(value):
    return re.sub(r'[^\w]', '', (value or '').casefold())


def identity(event):
    # Missing venues cannot establish an identity across publishers.
    return '|'.join(normalized(str(event.get(k) or '')) for k in ('title', 'start', 'venue'))


class Database:
    def __init__(self, path=None):
        self.path = Path(path or ROOT / 'data/events.sqlite')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as con:
            con.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, fingerprint TEXT, data TEXT NOT NULL, overrides TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS events_fingerprint ON events(fingerprint);
                CREATE TABLE IF NOT EXISTS refs(source_id TEXT, external_id TEXT, event_id TEXT, url TEXT, checked_at TEXT, snapshot TEXT, PRIMARY KEY(source_id,external_id));
                CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
                CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, url TEXT UNIQUE, title TEXT, found_on TEXT, status TEXT DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS geocache(address TEXT PRIMARY KEY,data TEXT NOT NULL);
            ''')
            if 'snapshot' not in {row['name'] for row in con.execute('PRAGMA table_info(refs)')}:
                con.execute('ALTER TABLE refs ADD COLUMN snapshot TEXT')
            registry = json.loads((ROOT / 'docs/research/darmstadt-sources.json').read_text())
            sources = registry['sources'] + [dict(source) for source in EXTRA_SOURCES
                                             if source['id'] not in {item['id'] for item in registry['sources']}]
            for source in sources:
                sid = source['id']
                source.update(implemented=sid in COLLECTORS, enabled=sid in COLLECTORS,
                              method=COLLECTORS[sid][0] if sid in COLLECTORS else 'Discovered · manual integration',
                              last_attempt=None, last_success=None, error=None, event_count=0)
                con.execute('INSERT OR IGNORE INTO sources VALUES (?,?)', (sid, json.dumps(source)))

    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        return con

    def get_meta(self, key, default=None):
        with self.connect() as con:
            row = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        with self.connect() as con:
            con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps(value)))

    def checkpoint(self):
        with self.connect() as con:
            row = con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if row is not None and row[0] != 0:
                raise RuntimeError('database busy during checkpoint')

    def sources(self):
        with self.connect() as con:
            return [json.loads(r[0]) for r in con.execute('SELECT data FROM sources')]

    def update_source(self, sid, **fields):
        with self.lock, self.connect() as con:
            row = con.execute('SELECT data FROM sources WHERE id=?', (sid,)).fetchone()
            if not row:
                raise KeyError(sid)
            data = json.loads(row[0])
            data.update(fields)
            con.execute('UPDATE sources SET data=? WHERE id=?', (json.dumps(data), sid))

    @staticmethod
    def _source_names(con):
        return {row['id']: json.loads(row['data'])['name'] for row in con.execute('SELECT id,data FROM sources')}

    @staticmethod
    def _provenance(row, names):
        record = dict(row)
        snapshot = record.pop('snapshot')
        record['name'] = names.get(record['source_id'], 'Manual submission')
        record['snapshot'] = json.loads(snapshot) if snapshot else None
        return record

    def _event(self, row, names, provenance):
        data = json.loads(row['data'])
        data.update({key: value for key, value in json.loads(row['overrides']).items() if not key.startswith('_')})
        data['id'] = row['id']
        data['provenance'] = provenance
        return data

    def event(self, eid):
        with self.connect() as con:
            row = con.execute('SELECT * FROM events WHERE id=?', (eid,)).fetchone()
            if not row:
                raise KeyError(eid)
            names = self._source_names(con)
            provenance = [self._provenance(record, names) for record in con.execute(
                'SELECT source_id,external_id,url,checked_at,snapshot FROM refs WHERE event_id=? ORDER BY checked_at DESC',
                (eid,))]
            return self._event(row, names, provenance)

    def events(self, status=None):
        with self.connect() as con:
            rows = con.execute('SELECT * FROM events').fetchall()
            names = self._source_names(con)
            provenance = {row['id']: [] for row in rows}
            for record in con.execute(
                    'SELECT source_id,external_id,event_id,url,checked_at,snapshot FROM refs ORDER BY checked_at DESC'):
                if record['event_id'] in provenance:
                    provenance[record['event_id']].append(self._provenance(record, names))
            events = [self._event(row, names, provenance[row['id']]) for row in rows]
        return sorted((e for e in events if status is None or e['status'] == status), key=lambda e: e.get('start') or '9999')

    @staticmethod
    def _review_signature(records):
        facts = []
        for source_id, external_id, snapshot in records:
            if snapshot:
                data = json.loads(snapshot) if isinstance(snapshot, str) else snapshot
                facts.append((source_id, external_id, tuple(data.get(key) for key in APPROVAL_FIELDS)))
        return hashlib.sha256(json.dumps(sorted(facts), ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def _disagreements(snapshots):
        return [key for key in MATERIAL_FIELDS
                if len({json.dumps(snapshot.get(key), sort_keys=True) for snapshot in snapshots}) > 1]

    def upsert_event(self, event, source_id, checked_at):
        event = dict(event, last_checked=checked_at)
        external_id = event.pop('external_id')
        url = event.pop('url', '')
        source_snapshot = dict(event)
        fp = identity(event)
        with self.lock, self.connect() as con:
            ref = con.execute('SELECT event_id,snapshot FROM refs WHERE source_id=? AND external_id=?',
                              (source_id, external_id)).fetchone()
            if ref is None and source_id != 'manual':
                prefix = external_id + '|'
                legacy_candidates = con.execute(
                    'SELECT external_id,event_id,snapshot FROM refs '
                    'WHERE source_id=? AND substr(external_id,1,?)=?',
                    (source_id, len(prefix), prefix)).fetchall()
                if len(legacy_candidates) == 1:
                    legacy = legacy_candidates[0]
                    candidate = con.execute('SELECT data FROM events WHERE id=?',
                                            (legacy['event_id'],)).fetchone()
                    previous_data = json.loads(candidate['data']) if candidate else {}
                    if legacy['external_id'] == prefix + str(previous_data.get('start')):
                        con.execute('DELETE FROM refs WHERE source_id=? AND external_id=?',
                                    (source_id, legacy['external_id']))
                        ref = legacy
            row = con.execute('SELECT * FROM events WHERE id=?', (ref['event_id'],)).fetchone() if ref else None
            if row is None and event.get('venue'):
                row = con.execute('SELECT * FROM events WHERE fingerprint=?', (fp,)).fetchone()
            if row:
                eid = row['id']
                old = json.loads(row['data'])
                overrides = json.loads(row['overrides'])
                previous = json.loads(ref['snapshot']) if ref and ref['snapshot'] else (old if ref else None)
                location_changed = bool(previous and any(
                    previous.get(key) != event.get(key) for key in LOCATION_FIELDS))
                approval_facts_changed = bool(previous and any(
                    previous.get(key) != event.get(key) for key in APPROVAL_FIELDS))

                records = []
                replaced = False
                for record in con.execute(
                        'SELECT source_id,external_id,snapshot FROM refs WHERE event_id=?', (eid,)):
                    if record['source_id'] == source_id and record['external_id'] == external_id:
                        records.append((source_id, external_id, source_snapshot))
                        replaced = True
                    elif record['snapshot']:
                        records.append((record['source_id'], record['external_id'], record['snapshot']))
                if not replaced:
                    records.append((source_id, external_id, source_snapshot))
                snapshots = [json.loads(snapshot) if isinstance(snapshot, str) else snapshot
                             for _, _, snapshot in records]
                differences = self._disagreements(snapshots)

                if differences:
                    for key in MATERIAL_FIELDS:
                        event[key] = old.get(key)
                    event['status'] = 'review'
                    event['review_reason'] = 'Sources disagree on ' + ', '.join(differences)
                    if any(key in differences for key in LOCATION_FIELDS):
                        for key in ('lat', 'lon', 'coordinate_evidence'):
                            event[key] = None if location_changed else old.get(key)

                signature = self._review_signature(records)
                approved = overrides.get('_source_review_signature')
                needs_new_review = bool(differences) or (
                    approval_facts_changed and source_snapshot.get('status') == 'review')
                if needs_new_review and approved and approved != signature:
                    overrides.pop('status', None)
                    overrides.pop('review_reason', None)
                    overrides.pop('_source_review_signature', None)

                carry = ('lat', 'lon', 'coordinate_evidence') if not location_changed else ()
                for key in carry:
                    if event.get(key) is None and old.get(key) is not None:
                        event[key] = old[key]

                if location_changed and not any(key in overrides for key in LOCATION_FIELDS):
                    for key in ('lat', 'lon', 'coordinate_evidence'):
                        overrides.pop(key, None)

                con.execute('UPDATE events SET data=?,fingerprint=?,overrides=? WHERE id=?',
                            (json.dumps(event), identity(event), json.dumps(overrides), eid))
            else:
                eid = hashlib.sha256(f'{source_id}|{external_id}'.encode()).hexdigest()[:20]
                con.execute('INSERT INTO events(id,fingerprint,data) VALUES (?,?,?)', (eid, fp, json.dumps(event)))
            con.execute('INSERT OR REPLACE INTO refs(source_id,external_id,event_id,url,checked_at,snapshot) VALUES (?,?,?,?,?,?)',
                        (source_id, external_id, eid, url, checked_at, json.dumps(source_snapshot)))
        return eid

    def edit_event(self, eid, changes):
        with self.lock, self.connect() as con:
            row = con.execute('SELECT data,overrides FROM events WHERE id=?', (eid,)).fetchone()
            if not row:
                raise KeyError(eid)
            data = json.loads(row['data'])
            overrides = json.loads(row['overrides'])
            effective = data | {key: value for key, value in overrides.items() if not key.startswith('_')}
            location_changed = any(
                key in changes and changes[key] != effective.get(key) for key in LOCATION_FIELDS)
            overrides.update(changes)
            if location_changed:
                if not {'lat', 'lon'} <= changes.keys():
                    overrides['lat'] = None
                    overrides['lon'] = None
                if 'coordinate_evidence' not in changes:
                    overrides['coordinate_evidence'] = None
            if changes.get('status') == 'published':
                records = con.execute(
                    'SELECT source_id,external_id,snapshot FROM refs WHERE event_id=?', (eid,)).fetchall()
                overrides['_source_review_signature'] = self._review_signature(
                    [(record['source_id'], record['external_id'], record['snapshot']) for record in records])
            elif 'status' in changes:
                overrides.pop('_source_review_signature', None)
            con.execute('UPDATE events SET overrides=? WHERE id=?', (json.dumps(overrides), eid))
        return self.event(eid)

    def candidate(self, url, title, found_on):
        with self.connect() as con:
            con.execute('INSERT OR IGNORE INTO candidates(url,title,found_on) VALUES (?,?,?)', (url, title[:200], found_on))

    def candidates(self):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM candidates ORDER BY id DESC LIMIT 300')]

    def edit_candidate(self, cid, status):
        with self.connect() as con:
            cur = con.execute('UPDATE candidates SET status=? WHERE id=?', (status, cid))
            if not cur.rowcount:
                raise KeyError(cid)

    def geocache(self, address, value=None):
        with self.connect() as con:
            if value is not None:
                con.execute('INSERT OR REPLACE INTO geocache VALUES (?,?)', (address, json.dumps(value)))
            row = con.execute('SELECT data FROM geocache WHERE address=?', (address,)).fetchone()
            return json.loads(row[0]) if row else None
