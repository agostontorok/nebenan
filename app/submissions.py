import base64
import binascii
import uuid
from datetime import datetime

from .collect import base_event, now_local


class SubmissionError(ValueError):
    """A manual submission could not be accepted as given."""


def validate_publication(event):
    if (event.get('lat') is None) != (event.get('lon') is None):
        raise SubmissionError('Provide both latitude and longitude')
    if event.get('scale') != 'unknown' and not (event.get('scale_evidence') or '').strip():
        raise SubmissionError('Describe the source evidence or reviewed estimate for event size')
    if event.get('end') and event.get('start') and datetime.fromisoformat(event['end']) <= datetime.fromisoformat(event['start']):
        raise SubmissionError('End must be after start')
    if event.get('status') == 'published':
        if not event.get('title') or not event.get('start') or not (event.get('venue') or event.get('address')):
            raise SubmissionError('Publishing requires a title, start date/time, and event location')


def store_poster(db, data, extension):
    folder = db.path.parent / 'posters'
    folder.mkdir(exist_ok=True)
    filename = str(uuid.uuid4()) + extension
    (folder / filename).write_bytes(data)
    return '/api/posters/' + filename


def _poster_bytes(poster_data, poster_ext):
    if poster_data is None:
        return None
    if isinstance(poster_data, str):
        kind, encoded = poster_data.split(';base64,', 1)
        if kind not in ('data:image/png', 'data:image/jpeg'):
            raise SubmissionError('Only PNG and JPEG posters are supported')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SubmissionError(str(exc))
        png = kind.endswith('png')
    else:
        data = bytes(poster_data)
        png = poster_ext == '.png'
    if not ((png and data.startswith(b'\x89PNG\r\n\x1a\n')) or (not png and data.startswith(b'\xff\xd8\xff'))):
        raise SubmissionError('Poster is not a valid PNG/JPEG')
    return data, '.png' if png else '.jpg'


def submit_manual(db, fields, poster_data=None, poster_ext=None):
    fields = dict(fields)
    if not fields.get('title'):
        raise SubmissionError('A title is required; uncertain facts can be left blank')
    fields.pop('status', None)
    source_url = fields.pop('source_url', '') or ''
    poster = _poster_bytes(fields.pop('poster', poster_data), poster_ext)
    event = base_event(fields.pop('title'), fields.pop('start', None), **fields)
    event.update(status='review', review_reason='Manual submission · verify details against the announcement',
                 external_id=str(uuid.uuid4()), url=source_url)
    validate_publication(event)
    if poster:
        event['poster_url'] = store_poster(db, poster[0], poster[1])
    eid = db.upsert_event(event, 'manual', now_local().isoformat())
    stored = db.event(eid)
    stored['url'] = source_url
    return stored