import json
import os
import subprocess
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .collect import Collector, iso, text
from .db import Database, ROOT
from .network import validate_url
from .sources import TOPICS, SCALES
from .submissions import SubmissionError, submit_manual, validate_publication


class EventInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str | None = Field(None, max_length=300)
    start: str | None = None
    end: str | None = None
    all_day: bool | None = None
    venue: str | None = Field(None, max_length=500)
    address: str | None = Field(None, max_length=1000)
    description: str | None = Field(None, max_length=12000)
    topics: list[str] | None = None
    scale: str | None = None
    scale_evidence: str | None = Field(None, max_length=1000)
    price: str | None = Field(None, max_length=300)
    free: bool | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    cancelled: bool | None = None
    status: Literal['review', 'published', 'rejected'] | None = None
    source_url: str | None = Field(None, max_length=3000)
    poster: str | None = Field(None, max_length=6_000_000)

    @model_validator(mode='after')
    def validate_fields(self):
        if self.title is not None and not self.title.strip():
            raise ValueError('Title cannot be blank')
        for key in ('start', 'end'):
            value = getattr(self, key)
            if value:
                try:
                    setattr(self, key, iso(value))
                except (ValueError, TypeError):
                    raise ValueError(f'{key} must be an ISO date/time')
            elif value == '':
                setattr(self, key, None)
        if self.topics is not None and any(t not in TOPICS for t in self.topics):
            raise ValueError('Unknown topic')
        if self.scale is not None and self.scale not in SCALES:
            raise ValueError('Unknown scale')
        if self.source_url:
            validate_url(self.source_url)
        return self


class SourceSuggestion(BaseModel):
    url: str = Field(max_length=3000)
    title: str = Field(default='', max_length=200)


class SourceToggle(BaseModel):
    enabled: bool


class CandidateStatus(BaseModel):
    status: Literal['accepted', 'rejected']


def create_app(db=None, scheduling=True):
    db = db or Database(os.environ.get('DARMSTADT_DB'))
    collector = Collector(db)
    stop = threading.Event()

    def schedule():
        while not stop.is_set():
            if collector.due():
                collector.start()
            stop.wait(30)

    @asynccontextmanager
    async def lifespan(app):
        if scheduling:
            threading.Thread(target=schedule, daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title='Darmstadt Local', lifespan=lifespan)
    app.state.db, app.state.collector = db, collector
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_guard(request: Request, call_next):
        if request.method in ('POST', 'PATCH', 'PUT', 'DELETE'):
            origin = request.headers.get('origin')
            expected = f'{request.url.scheme}://{request.headers.get("host")}'
            if (origin and origin != expected) or request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'detail': 'Local changes require the same origin'}, status_code=403)
            if request.url.path not in ('/api/collect', '/api/push') and request.headers.get('content-type', '').split(';')[0] != 'application/json':
                return JSONResponse({'detail': 'Send application/json'}, status_code=415)
            if int(request.headers.get('content-length', '0')) > 6_100_000:
                return JSONResponse({'detail': 'Submission too large'}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.get('/api/events')
    def events():
        return {'events': db.events('published')}

    @app.get('/api/review')
    def review():
        return {'events': db.events('review')}

    @app.get('/api/status')
    def status():
        sources = db.sources()
        events = db.events()
        return dict(running=collector.lock.locked(), last_run=db.get_meta('last_run'), next_due=db.get_meta('next_due'),
                    last_result=db.get_meta('last_result'), source_count=len(sources),
                    active_sources=sum(s['enabled'] and s['implemented'] for s in sources),
                    event_count=sum(e['status'] == 'published' for e in events),
                    review_count=sum(e['status'] == 'review' for e in events),
                    collection_progress=collector.progress, capabilities={'social': False, 'ocr': False, 'web_search': False})

    @app.get('/api/sources')
    def sources():
        return {'sources': db.sources(), 'candidates': db.candidates()}

    @app.post('/api/collect', status_code=202)
    def collect():
        if not collector.start():
            raise HTTPException(409, 'An update is already running')
        return {'status': 'started'}

    @app.post('/api/push')
    def push():
        try:
            db.checkpoint()
        except Exception as exc:
            raise HTTPException(409, 'Database is busy; try again: ' + str(exc))
        git_root = str(ROOT)
        status = subprocess.run(['git', '-C', git_root, 'status', '--porcelain', '--', 'data/events.sqlite'],
                                capture_output=True, text=True)
        if not status.stdout.strip():
            return {'status': 'unchanged'}
        for argv in (
            ['git', '-C', git_root, 'add', 'data/events.sqlite'],
            ['git', '-C', git_root, 'commit', '-m', 'events: publish review state'],
        ):
            result = subprocess.run(argv, capture_output=True, text=True)
            if result.returncode:
                raise HTTPException(500, result.stderr.strip() or 'git command failed')
        branch = subprocess.run(['git', '-C', git_root, 'rev-parse', '--abbrev-ref', 'HEAD'],
                                capture_output=True, text=True).stdout.strip()
        result = subprocess.run(['git', '-C', git_root, 'push', 'origin', branch],
                                capture_output=True, text=True)
        if result.returncode:
            raise HTTPException(500, result.stderr.strip() or 'git push failed')
        return {'status': 'pushed', 'branch': branch}

    @app.post('/api/submissions', status_code=201)
    def submission(payload: EventInput):
        try:
            return submit_manual(db, payload.model_dump(exclude_unset=True))
        except SubmissionError as exc:
            raise HTTPException(422, str(exc))

    @app.get('/api/posters/{filename}')
    def poster(filename: str):
        if '/' in filename or '\\' in filename or '..' in filename or not filename.endswith(('.png', '.jpg')):
            raise HTTPException(404)
        path = db.path.parent / 'posters' / filename
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.patch('/api/events/{eid}')
    def edit(eid: str, payload: EventInput):
        try:
            event = db.event(eid)
        except KeyError:
            raise HTTPException(404, 'Event not found')
        changes = payload.model_dump(exclude_unset=True, exclude={'source_url', 'poster'})
        for key in ('title', 'venue', 'address', 'description', 'scale_evidence', 'price'):
            if key in changes and changes[key] is not None:
                changes[key] = text(changes[key])
        try:
            validate_publication(event | changes)
        except SubmissionError as exc:
            raise HTTPException(422, str(exc))
        if changes.get('status') == 'published':
            changes['review_reason'] = ''
        return db.edit_event(eid, changes)

    @app.post('/api/sources/suggest', status_code=201)
    def suggest(payload: SourceSuggestion):
        try:
            validate_url(payload.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        db.candidate(payload.url, payload.title, 'Manual suggestion')
        return {'status': 'pending'}

    @app.patch('/api/sources/{sid}')
    def toggle_source(sid: str, payload: SourceToggle):
        source = next((s for s in db.sources() if s['id'] == sid), None)
        if not source:
            raise HTTPException(404, 'Source not found')
        if not source['implemented']:
            raise HTTPException(422, 'This source needs an adapter before it can be enabled')
        db.update_source(sid, enabled=payload.enabled)
        return {'status': 'saved'}

    @app.patch('/api/candidates/{cid}')
    def candidate_status(cid: int, payload: CandidateStatus):
        try:
            db.edit_candidate(cid, payload.status)
        except KeyError:
            raise HTTPException(404, 'Candidate not found')
        return {'status': payload.status}

    dist = ROOT / 'web/dist'
    if dist.is_dir():
        app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    else:
        @app.get('/')
        def missing_build():
            return {'message': 'Build the frontend with ./run.sh', 'api': '/docs'}
    return app


app = create_app()
