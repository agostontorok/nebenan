"""Source extraction, conservative publication, and persistent weekly collection."""
import hashlib
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlsplit, urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from icalendar import Calendar
import recurring_ical_events

from .llm_extract import extract_events_from_html, strip_html
from .network import fetch as public_fetch, validate_url
from .sources import AREA_CENTROIDS, COLLECTORS, KRONE_ADDRESS, SUPPORTED_PLACES

TZ = ZoneInfo('Europe/Berlin')
log = logging.getLogger(__name__)
STREET_PATTERN = r'([\wÄÖÜäöüß .-]+(?:straße|strasse|str\.|gasse|weg|platz|allee)\s+\d+[a-zA-Z]?)'


def street_address(value):
    match = re.search(STREET_PATTERN, value, re.I)
    return match.group(1).strip() if match else None


def now_local():
    return datetime.now(TZ)


def text(value):
    return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)[:12000]


def iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            aware = value.replace(tzinfo=TZ)
            if aware.astimezone(timezone.utc).astimezone(TZ).replace(tzinfo=None) != value:
                raise ValueError('This Berlin local time does not exist during the daylight-saving transition')
            return aware.isoformat()
        return value.astimezone(TZ).isoformat()
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), TZ).isoformat()
    return iso(datetime.fromisoformat(str(value).replace('Z', '+00:00')))


def infer_topics(title, description):
    rules = {
        'music': r'konzert|jazz|musik|concert|band\b|disco|disko|dj\b|chor\b|singen',
        'culture': r'theater|kino|film|kunst|ausstellung|lesung|literatur|tanz|kultur|museum',
        'food': r'café|kaffee|frühstück|kochen|küche|essen\b|wein\b|brunch|mittagstisch',
        'social': r'quiz|spiel|schach|skat\b|doppelkopf|treff|bingo|stammtisch|gesellig|kennenlernen|begegnung|queer',
        'outdoors': r'rad(tour|eln)|fahrrad|wandern|yoga|sport|lauf|garten|natur|pilates|gymnastik',
        'family': r'kinder|familie|eltern|baby|jugend|mädchen|jungen|teens',
        'learning': r'workshop|vortrag|kurs|lernen|repair|reparatur|seminar|beratung|sprache|sprach|sprechstunde|medien',
        'civic': r'demonstration|kundgebung|politik|klima|bürger|versammlung|solidarität|engagement',
    }
    def matches(value):
        return [topic for topic, pattern in rules.items() if re.search(r'\b(?:' + pattern + ')', value, re.I)]
    # The title supplies the primary topic; descriptive mentions add secondary
    # topics. Word boundaries prevent e.g. "Hessen" matching "essen".
    return list(dict.fromkeys(matches(title) + matches(description)))


def local_coordinates(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
        if 49.75 <= lat <= 49.99 and 8.53 <= lon <= 8.80:
            return lat, lon
    except (ValueError, TypeError):
        pass
    return None, None


def infer_area(value):
    """Return the supported municipality evidenced by a venue/address string."""
    value = str(value or '').casefold()
    postal_codes = re.findall(r'\b\d{5}\b', value)
    for area, config in SUPPORTED_PLACES.items():
        if any(re.search(r'\b' + re.escape(alias) + r'\b', value, re.I) for alias in config['aliases']):
            return area
        if any(code.startswith(prefix) for code in postal_codes for prefix in config['postal_prefixes']):
            return area
    return None


def street_city(value):
    """Return (street, city) resolved from a venue/address, matching geocode."""
    street = street_address(value or '')
    city = infer_area(value or '') or 'Darmstadt'
    return street, city


def base_event(title, start, venue='', address='', description='', end=None, **extra):
    title, venue, address, description = map(text, (title, venue, address, description))
    area = infer_area(address + ' ' + venue)
    valid_local = area is not None
    reason = []
    if not title:
        reason.append('Missing title')
    if not start:
        reason.append('Missing start date')
    if not venue and not address:
        reason.append('Missing event location')
    if not valid_local:
        reason.append('Darmstadt area location needs confirmation')
    if re.findall(r'\b\d{5}\b', address) and area is None:
        reason.append('Regional address needs confirmation')
    if re.search(r'\bonline\b|\bzoom\b|wird noch|noch bekannt|tba\b', venue + ' ' + address, re.I):
        reason.append('Online or unresolved venue')
    title_street, location_street = street_address(title), street_address(address)
    if title_street and location_street:
        def normalize_street(value):
            return re.sub(r'[^\w]', '', value.casefold().replace('straße', 'str').replace('strasse', 'str'))
        if normalize_street(title_street) != normalize_street(location_street):
            reason.append('Title and calendar address conflict')
    if location_street:
        def street_key(value):
            return re.sub(r'[^\w]', '', value.casefold().replace('straße', 'str').replace('strasse', 'str'))
        for mention in re.findall(STREET_PATTERN, description, re.I):
            if street_key(mention) != street_key(location_street):
                reason.append('Description and calendar address need comparison')
                break
    centroid = AREA_CENTROIDS.get(area)
    event = dict(title=title, start=start, end=end if end and start and datetime.fromisoformat(end) > datetime.fromisoformat(start) else None,
                 all_day=False, venue=venue, address=address, description=description[:2500],
                 topics=infer_topics(title, description), scale='unknown', scale_evidence='',
                 price=None, free=None, lat=centroid[0] if centroid else None,
                 lon=centroid[1] if centroid else None,
                 coordinate_evidence='Approximate municipality centre; confirm exact venue' if centroid else None,
                 image_url=None,
                 status='review' if reason else 'published', cancelled=False, area=area or '',
                 review_reason='; '.join(reason))
    event.update(extra)
    return event


def safe_link(value, fallback=''):
    try:
        validate_url(str(value))
        return str(value)
    except (ValueError, TypeError):
        return fallback


GENERIC_IMAGE_HINT = re.compile(
    r'(?:^|[/_.-])(favicon|favicons|logo|logos|brand|branding|sprite|sprites|icon|icons)(?:$|[/_.-])',
    re.I,
)


def _image_values(value):
    """Yield image URL candidates from JSON-LD image values."""
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _image_values(item)
    elif isinstance(value, dict):
        for key in ('url', 'contentUrl', 'thumbnailUrl'):
            if value.get(key):
                yield from _image_values(value[key])
    elif isinstance(value, str):
        yield value


def _safe_image_url(value, page_url):
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = urljoin(page_url, value.strip()).split('#', 1)[0]
    try:
        parsed = validate_url(candidate)
    except (ValueError, TypeError):
        return None
    path = parsed.path or ''
    if GENERIC_IMAGE_HINT.search(path):
        return None
    return candidate


def extract_event_image(soup, item=None, page_url=''):
    """Select one explicitly declared, safe image URL for an event page.

    JSON-LD is preferred, followed by Open Graph/Twitter metadata and then a
    scoped event image. The caller supplies the already fetched page or event
    fragment, so this helper never performs another network request.
    """
    if item:
        for value in _image_values(item.get('image')):
            image_url = _safe_image_url(value, page_url)
            if image_url:
                return image_url

    for selector, attribute in (
        ('meta[property="og:image"]', 'content'),
        ('meta[name="twitter:image"]', 'content'),
    ):
        for node in soup.select(selector):
            image_url = _safe_image_url(node.get(attribute), page_url)
            if image_url:
                return image_url

    image_nodes = soup.select(
        '[itemprop="image"], article img, .event img, .event-card img, main img, img'
    )[:40]
    for node in image_nodes:
        hints = ' '.join(str(node.get(key) or '') for key in ('alt', 'class', 'id', 'title'))
        if re.search(r'\b(?:favicon|logo|branding|sprite|icon)\b', hints, re.I):
            continue
        for attribute in ('src', 'data-src', 'data-lazy-src', 'data-original', 'srcset', 'data-srcset'):
            value = node.get(attribute)
            candidates = (
                [part.strip().split()[0] for part in str(value).split(',') if part.strip()]
                if attribute.endswith('srcset') and value
                else [value]
            )
            for candidate in candidates:
                image_url = _safe_image_url(candidate, page_url)
                if image_url:
                    return image_url
    return None


def parse_ical(raw, source_id, start, end):
    if b'BEGIN:VCALENDAR' not in raw[:1000]:
        raise ValueError('Source did not return an iCalendar')
    cal = Calendar.from_ical(raw)
    if not cal.walk('VEVENT'):
        raise ValueError('Calendar contains no event records')
    recurring_uids = set()
    for component in cal.walk('VEVENT'):
        rule = component.get('RRULE')
        if rule:
            freq = str(rule.get('FREQ', [''])[0]).upper()
            # Public events need day-or-coarser recurrence; reject dense schedules
            # before the library can allocate an unbounded occurrence list.
            if freq not in ('DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY') or any(key in rule for key in ('BYSECOND', 'BYMINUTE', 'BYHOUR')):
                raise ValueError('Unsupported dense recurrence frequency')
        if rule or component.get('RDATE') or component.get('RECURRENCE-ID'):
            recurring_uids.add(str(component.get('UID')))
    occurrences = recurring_ical_events.of(cal).between(start, end)
    if len(occurrences) > 5000:
        raise ValueError('Calendar exceeds the occurrence limit')
    events = []
    for component in occurrences:
        dt = component.decoded('DTSTART', None)
        if dt is None:
            continue
        start_iso = iso(dt)
        if start_iso < iso(start.replace(hour=0, minute=0, second=0, microsecond=0)):
            # Keep all-day/multi-day events that overlap the query.
            until = component.decoded('DTEND', None)
            if not until or iso(until) <= iso(start):
                continue
        location = text(component.get('LOCATION', ''))
        description = text(component.get('DESCRIPTION', ''))
        end_dt = component.decoded('DTEND', None)
        recurrence_id = component.decoded('RECURRENCE-ID', None)
        uid = str(component.get('UID') or hashlib.sha256(component.to_ical()).hexdigest())
        external_id = uid + ('|' + iso(recurrence_id) if recurrence_id and uid in recurring_uids else '')
        attachments = component.get('ATTACH')
        attachments = attachments if isinstance(attachments, list) else [attachments]
        image_url = next(
            (_safe_image_url(str(attachment), COLLECTORS[source_id][1])
             for attachment in attachments if attachment),
            None,
        )
        event = base_event(component.get('SUMMARY'), start_iso, venue=location.split(',')[0].split(' @ ')[0],
                           address=location, description=description, end=iso(end_dt) if end_dt else None,
                           external_id=external_id, all_day=not isinstance(dt, datetime),
                           cancelled=str(component.get('STATUS', '')).upper() == 'CANCELLED',
                           url=safe_link(component.get('URL', ''), COLLECTORS[source_id][1]),
                           image_url=image_url)
        geo = component.get('GEO')
        if geo:
            event['lat'], event['lon'] = local_coordinates(geo.latitude, geo.longitude)
            if event['lat'] is not None:
                event['coordinate_evidence'] = 'Source iCalendar GEO'
        # Only explicit price text; USD-zero metadata seen in research is not trusted.
        cost = component.get('X-COST')
        if cost:
            event['price'] = text(cost)[:120]
        else:
            price_line = re.search(r'(?:Kosten|Eintritt):\s*([^\n]{1,120})', description, re.I)
            if price_line:
                event['price'] = price_line.group(1).strip()
        price_text = (event['price'] or '').strip().casefold().rstrip('.')
        explicit_free_line = re.search(r'(?im)^\s*(?:eintritt(?: ist)?|kosten)\s*:?\s*(?:frei|kostenlos|kostenfrei)\s*[.!]?\s*$', description)
        if price_text in ('frei', 'kostenlos', 'kostenfrei', '0', '0 €', '0,00 €', '0.00 €') or explicit_free_line:
            event['free'] = True
            event['price'] = event['price'] or 'Eintritt frei (source description)'
        elif re.search(r'\b[1-9]\d*(?:[,.]\d+)?\s*(?:€|EUR\b|Euro\b)', event['price'] or '', re.I):
            event['free'] = False
        events.append(event)
    return events


def parse_jsonld(raw, source_id, start, end):
    soup = BeautifulSoup(raw, 'html.parser')
    items = []

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            types = value.get('@type', [])
            types = [types] if isinstance(types, str) else types
            if any(t == 'Event' or t.endswith('Event') for t in types):
                items.append(value)
            for key in ('@graph', 'itemListElement', 'item'):
                if key in value:
                    visit(value[key])

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            visit(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError, TypeError):
            continue
    if not items:
        raise ValueError('No Event JSON-LD found')
    events = []
    for item in items:
        try:
            dt = iso(item['startDate'])
        except (ValueError, KeyError, TypeError):
            continue
        if not iso(start.replace(hour=0, minute=0, second=0, microsecond=0)) <= dt < iso(end):
            continue
        loc = item.get('location') or {}
        loc = loc if isinstance(loc, dict) else {'name': text(loc)}
        addr = loc.get('address', '')
        if isinstance(addr, dict):
            addr = ', '.join(str(addr.get(k) or '') for k in ('streetAddress', 'postalCode', 'addressLocality'))
        if source_id == 'goldene-krone':
            addr = KRONE_ADDRESS
        try:
            until = iso(item['endDate']) if item.get('endDate') else None
        except ValueError:
            until = None
        url = safe_link(item.get('url'), COLLECTORS[source_id][1])
        event = base_event(item.get('name'), dt, venue=text(loc.get('name') or 'Goldene Krone'), address=addr,
                           description=item.get('description', ''), end=until,
                           external_id=str(item.get('@id') or hashlib.sha256((str(item.get('name')) + dt + text(loc.get('name'))).encode()).hexdigest()),
                           url=url, image_url=extract_event_image(soup, item, url),
                           cancelled='EventCancelled' in str(item.get('eventStatus', '')))
        events.append(event)
    return events


def _parse_de_date(value, default_year):
    value = re.sub(r'\s+', '', str(value or ''))
    match = re.fullmatch(r'(\d{1,2})\.(\d{1,2})\.(\d{2,4})?', value)
    if not match:
        return None
    year = int(match.group(3) or default_year)
    if year < 100:
        year += 2000
    try:
        return date(year, int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None


def _event_in_window(start_dt, end_dt, start, end):
    return start_dt < end and (end_dt or start_dt + timedelta(minutes=1)) > start


def parse_city_html(raw, source_id, start, end):
    """Parse the public Griesheim and Weiterstadt HTML calendars.

    Both pages expose human readable dates rather than a feed.  We preserve
    multi day ranges and use the municipality as explicit location evidence;
    an exact street address can still be added from the admin form.
    """
    soup = BeautifulSoup(raw, 'html.parser')
    if source_id == 'griesheim-city':
        rows = soup.select('.calendar .row')
        events = []
        for row in rows:
            link = row.select_one('h2 a[href]')
            heading = row.select_one('h2')
            date_line = row.select_one('h4')
            if not link or not heading or not date_line:
                continue
            title = text(heading.get_text(' ', strip=True))
            info = text(date_line.get_text(' ', strip=True))
            dates = re.findall(r'\d{1,2}\.\d{1,2}\.\d{2,4}', info)
            if not dates:
                continue
            first = _parse_de_date(dates[0], start.year)
            last = _parse_de_date(dates[-1], start.year) if len(dates) > 1 else first
            if not first:
                continue
            times = re.findall(r'\b\d{1,2}:\d{2}\b', info)
            start_dt = datetime.combine(first, datetime.min.time(), TZ)
            end_dt = None
            all_day = not times
            if times:
                hour, minute = map(int, times[0].split(':'))
                start_dt = start_dt.replace(hour=hour, minute=minute)
                if len(times) > 1:
                    eh, em = map(int, times[1].split(':'))
                    end_dt = datetime.combine(last or first, datetime.min.time(), TZ).replace(hour=eh, minute=em)
            elif last:
                end_dt = datetime.combine(last + timedelta(days=1), datetime.min.time(), TZ)
            if not _event_in_window(start_dt, end_dt, start, end):
                continue
            summary = row.select_one('p')
            event = base_event(title, iso(start_dt), venue='', address='Griesheim',
                               description=summary.get_text(' ', strip=True) if summary else '',
                               end=iso(end_dt) if end_dt else None,
                               external_id='griesheim:' + link['href'].rstrip('/').split('/')[-1],
                               url=safe_link(urljoin(COLLECTORS[source_id][1], link['href']), COLLECTORS[source_id][1]),
                               image_url=extract_event_image(row, page_url=COLLECTORS[source_id][1]),
                               all_day=all_day)
            events.append(event)
        return events

    if source_id != 'weiterstadt-city':
        raise ValueError('Unsupported city calendar')
    events = []
    for panel in soup.select('.panel-group .panel'):
        date_node = panel.select_one('.date')
        title_node = panel.select_one('.event-title')
        body = panel.select_one('.event-container, .panel-body')
        if not date_node or not title_node or not body:
            continue
        date_text = text(date_node.get_text(' ', strip=True)).replace('–', '-').replace('—', '-')
        dates = re.findall(r'\d{1,2}\.\d{1,2}\.(?:\d{2,4})?', date_text)
        if not dates:
            continue
        first = _parse_de_date(dates[0], start.year)
        last = _parse_de_date(dates[-1], first.year if first else start.year) if len(dates) > 1 else first
        if not first:
            continue
        body_text = text(body.get_text(' ', strip=True))
        begin_match = re.search(r'Beginn:\s*(\d{1,2}:\d{2})', body_text, re.I)
        end_match = re.search(r'Ende:\s*(\d{1,2}:\d{2})', body_text, re.I)
        venue_match = re.search(r'Ort:\s*(.*?)(?=\s+Veranstalter:|$)', body_text, re.I)
        venue = venue_match.group(1).strip() if venue_match else ''
        if venue and not infer_area(venue):
            venue += ', Weiterstadt'
        description = ' '.join(p.get_text(' ', strip=True) for p in body.select('hr ~ p'))
        start_dt = datetime.combine(first, datetime.min.time(), TZ)
        all_day = begin_match is None
        end_dt = None
        if begin_match:
            h, m = map(int, begin_match.group(1).split(':'))
            start_dt = start_dt.replace(hour=h, minute=m)
            if end_match:
                eh, em = map(int, end_match.group(1).split(':'))
                end_dt = datetime.combine(last or first, datetime.min.time(), TZ).replace(hour=eh, minute=em)
        elif last:
            end_dt = datetime.combine(last + timedelta(days=1), datetime.min.time(), TZ)
        if not _event_in_window(start_dt, end_dt, start, end):
            continue
        event = base_event(text(title_node.get_text(' ', strip=True)), iso(start_dt), venue=venue,
                           address=venue or 'Weiterstadt', description=description,
                           end=iso(end_dt) if end_dt else None, all_day=all_day,
                           external_id='weiterstadt:' + hashlib.sha256((date_text + text(title_node.get_text())).encode()).hexdigest()[:16],
                           url=COLLECTORS[source_id][1],
                           image_url=extract_event_image(panel, page_url=COLLECTORS[source_id][1]))
        events.append(event)
    return events


def parse_html_llm(raw, source_id, start, end):
    """Extract calendar entries from a human-readable website page via the local model.

    Every extracted event lands in the review queue: the local model is only a
    field extraction aid, the human editor confirms the listing before it is
    published on the public site.
    """
    soup = BeautifulSoup(raw, 'html.parser')
    page_url = None
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get('href'):
        page_url = urljoin(COLLECTORS[source_id][1], canonical['href'])
    page_url = page_url or COLLECTORS[source_id][1]
    events = []
    for item in extract_events_from_html(raw, page_url, start):
        item_start = datetime.fromisoformat(item['start'])
        item_end = datetime.fromisoformat(item['end']) if item.get('end') else None
        if not _event_in_window(item_start, item_end, start, end):
            continue
        event = base_event(
            item['title'], iso(item_start), venue=item['venue'], address=item['address'],
            description=item['description'], end=iso(item_end) if item_end else None,
            external_id='llm:' + item['external_id'], url=item['url'])
        event['status'] = 'published'
        event['ai_extracted'] = True
        event['review_reason'] = ''
        events.append(event)
    return events


class Collector:
    def __init__(self, db, fetch=public_fetch, now=now_local):
        self.db, self.fetch, self.now = db, fetch, now
        self.lock = threading.Lock()
        self.progress = ''

    def due(self):
        due = self.db.get_meta('next_due')
        return bool(due and datetime.fromisoformat(due) <= self.now())

    def start(self):
        if not self.lock.acquire(blocking=False):
            return False
        threading.Thread(target=self.run, kwargs={'_locked': True}, daemon=True).start()
        return True

    def run(self, source_ids=None, discover=True, geocode=True, _locked=False):
        if not _locked and not self.lock.acquire(blocking=False):
            return False
        checked = self.now()
        result = {'successes': 0, 'failures': 0, 'imported': 0, 'started_at': checked.isoformat()}
        try:
            sources = [s for s in self.db.sources() if s['implemented'] and s['enabled'] and (source_ids is None or s['id'] in source_ids)]
            for i, source in enumerate(sources):
                sid = source['id']
                self.progress = f'{i + 1}/{len(sources)} · {source["name"]}'
                self.db.update_source(sid, last_attempt=checked.isoformat())
                try:
                    method, url = COLLECTORS[sid]
                    if sid == 'weiterstadt-city':
                        url = re.sub(r'index\.php\?y=\d{4}', f'index.php?y={checked.year}', url)
                    raw = self.fetch(url)
                    window_start = checked.replace(hour=0, minute=0, second=0, microsecond=0)
                    window_end = checked + timedelta(days=90)
                    if method == 'ical':
                        events = parse_ical(raw, sid, window_start, window_end)
                    elif method == 'jsonld':
                        events = parse_jsonld(raw, sid, window_start, window_end)
                    elif method == 'llm':
                        events = parse_html_llm(raw, sid, window_start, window_end)
                    else:
                        events = parse_city_html(raw, sid, window_start, window_end)
                    for event in events:
                        self.db.upsert_event(event, sid, checked.isoformat())
                    starts = [e['start'] for e in events if e.get('start')]
                    self.db.update_source(sid, last_success=checked.isoformat(), error=None,
                                          event_count=len(events), horizon_start=min(starts) if starts else None,
                                          horizon_end=max(starts) if starts else None)
                    result['successes'] += 1
                    result['imported'] += len(events)
                    if discover:
                        try:
                            self.discover(source, raw if method == 'jsonld' else self.fetch(url))
                        except Exception as exc:
                            self.db.update_source(sid, discovery_error=str(exc)[:300])
                except Exception as exc:
                    log.warning('%s: %s', sid, exc)
                    self.db.update_source(sid, error=str(exc)[:300])
                    result['failures'] += 1
            if geocode:
                self.progress = 'Resolving event addresses · cached, up to 20 new lookups'
                try:
                    self.geocode(limit=20)
                except Exception as exc:
                    result['geocoding_error'] = str(exc)[:300]
            result['finished_at'] = self.now().isoformat()
            self.db.set_meta('last_result', result)
            self.db.set_meta('last_run', checked.isoformat())
            self.db.set_meta('next_due', (self.now() + timedelta(days=7)).isoformat())
        finally:
            self.progress = ''
            self.lock.release()
        return True

    def discover(self, source, raw):
        soup = BeautifulSoup(raw, 'html.parser')
        known = {urlsplit(s['url']).hostname for s in self.db.sources()}
        count = 0
        for link in soup.select('a[href]'):
            title = text(link.get_text(' ', strip=True))
            url = urljoin(source['url'], link['href']).split('#')[0]
            try:
                p = validate_url(url)
            except ValueError:
                continue
            if p.hostname in known or not re.search(r'veranstalt|kultur|verein|treff|initiative|festival|darmstadt|instagram|facebook', title + ' ' + url, re.I):
                continue
            if any(host in (p.hostname or '') for host in ('google.', 'wordpress.', 'youtube.', 'wikipedia.')):
                continue
            self.db.candidate(url, title or p.hostname, source['url'])
            count += 1
            if count >= 12:
                break

    def geocode(self, limit=20):
        """Resolve only explicit street addresses, cache misses too, one request/1.1 s.

        Nominatim policy: https://operations.osmfoundation.org/policies/nominatim/
        No autocomplete; each collection is bounded and queries run serially.
        """
        attempts = 0
        for event in self.db.events('published'):
            if event.get('lat') is not None and not str(event.get('coordinate_evidence') or '').startswith('Approximate'):
                continue
            addr = event.get('address') or ''
            # Extract a street+number, never turn an organiser name into a venue pin.
            street, city = street_city(addr)
            if not street:
                continue
            key = street.casefold() + ', ' + city.casefold()
            cached = self.db.geocache(key)
            if cached is None:
                if attempts >= limit:
                    continue
                attempts += 1
                url = 'https://nominatim.openstreetmap.org/search?' + urlencode({'street': street, 'city': city, 'country': 'Germany', 'format': 'jsonv2', 'limit': 2, 'addressdetails': 1})
                try:
                    data = json.loads(self.fetch(url))
                    cached = {'lat': None, 'lon': None}
                    match = next((row for row in data
                                  if row.get('address', {}).get('house_number')), None)
                    if match:
                        lat, lon = local_coordinates(match.get('lat'), match.get('lon'))
                        if lat is not None:
                            cached = {'lat': lat, 'lon': lon, 'evidence': match.get('display_name'), 'url': url}
                    self.db.geocache(key, cached)
                finally:
                    time.sleep(1.1)
            if cached and cached.get('lat') is not None:
                # Geocoding is collected data, not a permanent human override.
                with self.db.lock, self.db.connect() as con:
                    row = con.execute('SELECT data FROM events WHERE id=?', (event['id'],)).fetchone()
                    data = json.loads(row[0])
                    data.update(lat=cached['lat'], lon=cached['lon'], coordinate_evidence=cached.get('url'))
                    con.execute('UPDATE events SET data=? WHERE id=?', (json.dumps(data), event['id']))
