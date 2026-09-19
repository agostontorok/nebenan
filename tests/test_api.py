import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.db import Database
from app.submissions import SubmissionError, submit_manual


def test_submission_review_validation_and_persistence(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    with TestClient(create_app(db, scheduling=False)) as client:
        bad = client.post('/api/submissions', json={'title': 'Quiz', 'start': 'next Thursday'})
        assert bad.status_code == 422
        assert client.post('/api/submissions', json={'title': 'Quiz', 'start': '2026-03-29T02:30'}).status_code == 422
        created = client.post('/api/submissions', json={'title': 'Quiz', 'source_url': 'https://example.com/post', 'description': '<script>alert(1)</script>See source'})
        assert created.status_code == 201
        eid = created.json()['id']
        assert client.get('/api/events').json()['events'] == []
        assert len(client.get('/api/review').json()['events']) == 1
        assert client.patch('/api/events/' + eid, json={'status': 'published'}).status_code == 422
        assert client.patch('/api/events/' + eid, json={'scale': 'small'}).status_code == 422
        approved = client.patch('/api/events/' + eid, json={'start': '2026-09-16T19:00:00+02:00', 'venue': 'Café', 'address': 'Darmstadt', 'scale': 'small', 'scale_evidence': 'Reviewed by local admin', 'status': 'published'})
        assert approved.status_code == 200
        assert len(client.get('/api/events').json()['events']) == 1
    assert Database(db.path).event(eid)['status'] == 'published'


def test_local_mutations_reject_foreign_origin_and_bad_data(tmp_path):
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        assert client.post('/api/collect', headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.post('/api/submissions', content='{}', headers={'content-type': 'text/plain'}).status_code == 415
        assert client.post('/api/sources/suggest', json={'url': 'http://127.0.0.1', 'title': 'private'}).status_code == 422
        assert client.patch('/api/sources/partyamt', json={'enabled': True}).status_code == 422
        assert client.post('/api/submissions', json={'title': 'X', 'lat': 49.8}).status_code == 422
        assert client.post('/api/submissions', json={'title': 'X', 'poster': 'data:image/svg+xml;base64,PHN2Zz4='}).status_code == 422


def test_submit_manual_missing_title_and_persists_review(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    try:
        submit_manual(db, {'start': '2026-10-05T19:00:00+02:00'})
        assert False, 'expected SubmissionError'
    except SubmissionError:
        pass
    ok = submit_manual(db, {'title': 'Quiz', 'venue': 'Café'})
    assert ok['status'] == 'review'
    assert ok['url'] == ''
    assert len(db.events('review')) == 1


def test_submit_manual_accepts_raw_poster_bytes(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 16
    event = submit_manual(db, {'title': 'Photo', 'venue': 'Atelier'}, poster_data=png, poster_ext='.png')
    assert event['poster_url'].startswith('/api/posters/')
    assert event['poster_url'].endswith('.png')
    stored = (db.path.parent / 'posters' / event['poster_url'].split('/')[-1])
    assert stored.read_bytes() == png


def test_submit_manual_rejects_malformed_poster_uri(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    with pytest.raises(SubmissionError):
        submit_manual(db, {'title': 'X', 'venue': 'V'}, poster_data='data:image/png;notbase64')


def test_submissions_malformed_poster_uri_is_422(tmp_path):
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        response = client.post('/api/submissions', json={'title': 'X', 'poster': 'data:image/png;notbase64'})
    assert response.status_code == 422


import subprocess


class FakeGit:
    def __init__(self, status_stdout='M data/events.sqlite'):
        self.status_stdout = status_stdout
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        cmd = argv[3] if len(argv) > 3 and argv[1] == '-C' else argv[0]
        if cmd == 'status':
            stdout = self.status_stdout
        elif cmd == 'rev-parse':
            stdout = 'main\n'
        else:
            stdout = ''
        return subprocess.CompletedProcess(argv, 0, stdout=stdout)


def test_push_returns_unchanged_when_db_clean(tmp_path, monkeypatch):
    fake = FakeGit(status_stdout='')
    monkeypatch.setattr('app.main.subprocess.run', fake.run)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        assert client.post('/api/push').json() == {'status': 'unchanged'}
    assert any('status' in c and '--porcelain' in c for c in fake.calls)


def test_push_stages_only_db_and_pushes(tmp_path, monkeypatch):
    fake = FakeGit()
    monkeypatch.setattr('app.main.subprocess.run', fake.run)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        result = client.post('/api/push').json()
    assert result['status'] == 'pushed'
    assert result['branch'] == 'main'
    adds = [c for c in fake.calls if 'add' in c]
    assert adds and all(c[c.index('-C') + 1].startswith('/') for c in adds)
    assert any('data/events.sqlite' in c for c in adds)
    assert any('commit' in c for c in fake.calls)
    assert any('push' in c and 'origin' in c for c in fake.calls)
    assert not any('-wal' in ' '.join(c) for c in fake.calls)
