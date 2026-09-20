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


from app.import_issues import _poster, fetch_issues, import_issue, main, default_repo


def _issue(number, body, labels=()):
    return {'number': number, 'title': 't', 'body': body, 'url': f'https://github.com/o/r/issues/{number}',
            'labels': [{'name': label} for label in labels], 'comments': []}


def test_import_issue_dry_run_and_apply(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    calls = []
    monkeypatch.setattr('app.import_issues.gh_shell',
                        lambda args: calls.append([*args]) or 'https://github.com/o/r/issues/7')
    issue = _issue(7, '### Event title\nQuiz\n\n### Start (Berlin time)\n2026-10-05T19:00\n\n### Venue\nCafé')

    fields, note = import_issue(db, 'owner/repo', issue, apply=False)
    assert note == 'would import'
    assert fields['title'] == 'Quiz'
    assert calls == []

    event, note = import_issue(db, 'owner/repo', issue, apply=True)
    assert note == 'imported'
    assert event['status'] == 'review'
    assert len(db.events('review')) == 1
    labelled = [c for c in calls if '--add-label' in c]
    assert labelled and 'imported' in labelled[0]
    assert any(c[0] == 'issue' and c[1] == 'comment' for c in calls)
    assert any('7' in c for c in calls)


def test_import_issue_skips_existing_and_reports_errors(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: '')

    done, note = import_issue(db, 'owner/repo', _issue(1, '### Event title\nX\n', labels=('imported',)), apply=True)
    assert done is None and note == 'skipped (already imported)'

    bad, note = import_issue(db, 'owner/repo', _issue(2, '### Start (Berlin time)\n2026-10-05T19:00\n'), apply=True)
    assert bad is None and note.startswith('error:')


def test_import_issue_submission_error_posts_comment(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    calls = []
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: calls.append([*args]) or '')
    from app.submissions import SubmissionError
    def rejected(db, fields, **kwargs):
        raise SubmissionError('End must be after start')
    monkeypatch.setattr('app.import_issues.submit_manual', rejected)
    issue = _issue(9, '### Event title\nQuiz\n\n### Start (Berlin time)\n2026-10-05T19:00\n\n### End (optional)\n2026-10-05T18:00')

    result, note = import_issue(db, 'owner/repo', issue, apply=True)
    assert result is None
    assert note.startswith('error:')
    comments = [c for c in calls if c[0] == 'issue' and c[1] == 'comment']
    assert comments
    body = comments[0][comments[0].index('--body') + 1]
    assert body.startswith('Could not import: ')
    assert db.events('review') == []


def test_main_counts_only_newly_imported(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    issues = [
        _issue(1, '### Event title\nOne\n\n### Start (Berlin time)\n2026-10-05T19:00\n', labels=('imported',)),
        _issue(2, '### Event title\nTwo\n\n### Start (Berlin time)\n2026-10-05T19:00\n'),
        _issue(3, '### Event title\nThree\n\n### Start (Berlin time)\n2026-10-05T19:00\n'),
    ]
    monkeypatch.setattr('app.import_issues.fetch_issues', lambda repo: issues)
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: 'https://github.com/o/r/issues/1')
    imported, errors = main(repo='o/r', apply=True, db=db)
    assert imported == 2
    assert errors == 0


def test_main_exit_success_with_nothing_to_import(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    monkeypatch.setattr('app.import_issues.fetch_issues',
                        lambda repo: [_issue(1, '### Event title\nOne\n', labels=('imported',))])
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: '')
    imported, errors = main(repo='o/r', apply=True, db=db)
    assert imported == 0
    assert errors == 0


def test_main_exit_success_with_fresh_imports(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    monkeypatch.setattr('app.import_issues.fetch_issues',
                        lambda repo: [_issue(1, '### Event title\nOne\n\n### Start (Berlin time)\n2026-10-05T19:00\n')])
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: '')
    imported, errors = main(repo='o/r', apply=True, db=db)
    assert imported == 1
    assert errors == 0


def test_main_exit_dry_run_reports_would_import(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    monkeypatch.setattr('app.import_issues.fetch_issues',
                        lambda repo: [_issue(1, '### Event title\nOne\n\n### Start (Berlin time)\n2026-10-05T19:00\n')])
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: '')
    imported, errors = main(repo='o/r', apply=False, db=db)
    assert imported == 0
    assert errors == 0


def test_main_exit_failure_on_import_error(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    monkeypatch.setattr('app.import_issues.fetch_issues',
                        lambda repo: [_issue(1, '### Start (Berlin time)\n2026-10-05T19:00\n')])
    monkeypatch.setattr('app.import_issues.gh_shell', lambda args: '')
    imported, errors = main(repo='o/r', apply=True, db=db)
    assert imported == 0
    assert errors == 1


def test_main_gh_bookkeeping_failure_continues_and_reports(tmp_path, monkeypatch):
    db = Database(tmp_path / 'events.sqlite')
    issues = [
        _issue(4, '### Event title\nFour\n\n### Start (Berlin time)\n2026-10-05T19:00\n'),
        _issue(5, '### Event title\nFive\n\n### Start (Berlin time)\n2026-10-05T19:00\n'),
    ]

    def fake_gh_shell(args):
        if args[1] == 'edit' and args[2] == '4':
            raise SystemExit('gh failed: boom')
        return ''

    monkeypatch.setattr('app.import_issues.fetch_issues', lambda repo: issues)
    monkeypatch.setattr('app.import_issues.gh_shell', fake_gh_shell)
    imported, errors = main(repo='o/r', apply=True, db=db)
    assert imported == 2
    assert errors == 1
    assert len(db.events('review')) == 2


def test_poster_fetches_png_without_network(monkeypatch):
    png = b'\x89PNG\r\n\x1a\n' + b'0' * 16
    seen = []
    def fake_fetch(url):
        seen.append(url)
        return png
    monkeypatch.setattr('app.import_issues.public_fetch', fake_fetch)
    issue = {'body': '![poster](https://example.com/p.png)', 'comments': []}
    assert _poster(issue) == (png, '.png')
    assert seen == ['https://example.com/p.png']


def test_poster_returns_none_on_fetch_failure(monkeypatch):
    def fake_fetch(url):
        raise ConnectionError('no network')
    monkeypatch.setattr('app.import_issues.public_fetch', fake_fetch)
    issue = {'body': '![poster](https://example.com/p.png)', 'comments': []}
    assert _poster(issue) == (None, None)


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