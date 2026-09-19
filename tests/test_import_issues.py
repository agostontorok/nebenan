import json
import pytest

from app.import_issues import parse_issue_body
from app.db import Database


def test_parse_issue_body_maps_form_sections():
    body = """### Event title
Jazz im Herrngarten

### Start (Berlin time)
2026-10-05T19:00

### Venue
Herrngarten

### Admission
Free

### Price / admission details
10 EUR
"""
    assert parse_issue_body(body) == {
        'title': 'Jazz im Herrngarten',
        'start': '2026-10-05T19:00',
        'venue': 'Herrngarten',
        'free': True,
        'price': '10 EUR',
    }


def test_parse_issue_body_unknown_admission_and_blanks():
    body = "### Event title\nQuiz\n\n### Admission\nUnknown\n\n### End (optional)\n"
    fields = parse_issue_body(body)
    assert fields['title'] == 'Quiz'
    assert 'free' not in fields
    assert 'end' not in fields


def test_parse_issue_body_paid_admission():
    assert parse_issue_body('### Admission\nPaid\n') == {'free': False}


def test_parse_issue_body_keeps_inner_markdown_heading_in_description():
    body = "### Description / event text\nLine one\n### Highlights\npoint A\n"
    fields = parse_issue_body(body)
    assert fields['description'] == 'Line one\n### Highlights\npoint A'


from app.import_issues import fetch_issues, import_issue, main, default_repo


def _issue(number, body, labels=()):
    return {'number': number, 'title': 't', 'body': body, 'url': f'https://github.com/o/r/issues/{number}',
            'labels': [{'name': label} for label in labels], 'comments': []}


def test_import_issue_dry_run_and_apply(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    calls = []
    monkeypatch.setattr('app.import_issues.gh', lambda args: calls.append(args) or {'ok': True})
    issue = _issue(7, '### Event title\nQuiz\n\n### Start (Berlin time)\n2026-10-05T19:00\n\n### Venue\nCafé')

    fields, note = import_issue(db, 'owner/repo', issue, apply=False)
    assert note == 'would import'
    assert fields['title'] == 'Quiz'

    event, note = import_issue(db, 'owner/repo', issue, apply=True)
    assert note == 'imported'
    assert event['status'] == 'review'
    assert len(db.events('review')) == 1
    joins = [c for c in calls if c and c[0] == 'issue']
    assert any('--add-label' in c and 'imported' in c for c in joins)
    assert any(c[0] == 'issue' and c[1] == 'comment' for c in joins)


def test_import_issue_skips_existing_and_reports_errors(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    monkeypatch.setattr('app.import_issues.gh', lambda args: {'ok': True})

    done, note = import_issue(db, 'owner/repo', _issue(1, '### Event title\nX\n', labels=('imported',)), apply=True)
    assert done is None and note == 'skipped (already imported)'

    bad, note = import_issue(db, 'owner/repo', _issue(2, '### Start (Berlin time)\n2026-10-05T19:00\n'), apply=True)
    assert bad is None and note.startswith('error:')


def test_fetch_issues_uses_submission_label(monkeypatch):
    captured = {}
    def fake_gh(args):
        captured['args'] = args
        return []
    monkeypatch.setattr('app.import_issues.gh', fake_gh)
    assert fetch_issues('owner/repo') == []
    assert '--label' in captured['args'] and 'submission' in captured['args']


def test_default_repo_from_origin(monkeypatch):
    monkeypatch.setattr('app.import_issues.subprocess.run', lambda argv, **kw: type('P', (), {'stdout': 'git@github.com:agostontorok/nebenan.git\n'})())
    assert default_repo() == 'agostontorok/nebenan'
