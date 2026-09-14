from fastapi.testclient import TestClient
from app.main import create_app
from app.db import Database


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
