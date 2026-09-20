# Issue Intake and Editor Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let visitors share events as GitHub issues via a form template, import those issues into the local review queue with a CLI, add a local editor mode (Review + Admin only) to the existing app, and push the reviewed SQLite DB to GitHub with a single button.

**Architecture:** Submissions land in the GitHub repo as issues carrying the `submission` label. The importer reads them with the `gh` CLI, parses the issue-form markdown body, and stores each one through the same validate-and-insert path the `/api/submissions` endpoint uses (extracted into a new module that both share). The existing app gains a build-time `VITE_EDITOR` variant that shows only Review and Admin, plus a `POST /api/push` endpoint that checkpoints SQLite, stages only `data/events.sqlite`, commits, and pushes. The DB becomes tracked and public.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (WAL), GitHub CLI (`gh`), GitHub issue forms, Vite, React 19, TypeScript.

## Global Constraints

- No cloud credentials or new infrastructure. `gh` uses the existing user login; the app stores no token.
- `data/events.sqlite` becomes tracked; `-shm`, `-wal`, and `data/posters/` stay ignored.
- Only `data/events.sqlite` may ever be committed by the push endpoint; unrelated WIP is never staged.
- Reuse the exact submission validation (`base_event` → `validate_publication` → `db.upsert_event(..., 'manual', ...)`) for both the web endpoint and the CLI importer. See `app/main.py:159`.
- Tests never invoke the real `gh` CLI or the network; both are injected or monkeypatched.
- Keep existing test suites green: `PYTHONPATH=. .venv/bin/python -m pytest -q` and `cd web && npm test`, and `npm run build` must pass.
- Existing modified files `web/src/main.tsx` and `web/src/style.css` have unrelated uncommitted changes; do not stage or revert them, and never include them in push commits.

## File map

- Create `.github/ISSUE_TEMPLATE/event-share.yml`: issue form for sharing an event, sets `labels: ["submission"]`.
- Create `app/submissions.py`: `SubmissionError`, `validate_publication`, `store_poster`, `submit_manual` — the shared manual-submission pipeline.
- Create `app/import_issues.py`: CLI that fetches submission issues via `gh` and imports them.
- Create `tests/test_import_issues.py`: parser tests and a fake-`gh` import test.
- Create `web/src/vite-env.d.ts`: registers Vite client types so `import.meta.env` type-checks.
- Modify `app/main.py`: replace `/api/submissions` and `edit` validation with the shared helpers; add `POST /api/push`.
- Modify `app/db.py`: add `Database.checkpoint()`.
- Modify `tests/test_api.py`: add `/api/push` test with a fake git.
- Modify `run.sh`: editor-mode build (passes `VITE_EDITOR=1`).
- Modify `web/src/main.tsx`: editor-mode tab filter, hide Share/Sources/Discover, add Publish & push button in Admin.
- Modify `web/src/i18n.mjs`: add editor Admin + push copy in English and German.
- Modify `.gitignore`: un-ignore `data/events.sqlite`.
- Modify `README.md`: document the editor mode, import CLI, and share-via-issue flow.

## Reference: `EventInput` and the existing submission endpoint

`app/main.py:23-63` defines `EventInput` (title, start, end, all_day, venue, address, description, topics, scale, scale_evidence, price, free, lat, lon, cancelled, status, source_url, poster). `app/main.py:79-87` defines `validate_publication`, which raises `HTTPException`. `app/main.py:159-187` is the submission endpoint: it rejects a missing title, pops `status`/`source_url`/`poster`, calls `base_event(fields.pop('title'), fields.pop('start', None), **fields)`, forces `status='review'` with `external_id=uuid`, runs `validate_publication`, writes any poster as `data/posters/<uuid>.<ext>`, and calls `db.upsert_event(event, 'manual', now_local().isoformat())`.

### Task 1: Issue form template

**Files:**
- Create: `.github/ISSUE_TEMPLATE/event-share.yml`

- [ ] **Step 1: Write the issue form**

Create `.github/ISSUE_TEMPLATE/event-share.yml`:

```yaml
name: Share an event
description: Suggest an upcoming event for the Darmstadt calendar.
title: "[Event] "
labels: ["submission"]
body:
  - type: input
    id: title
    attributes:
      label: Event title
      placeholder: "Jazz im Herrngarten"
    validations:
      required: true
  - type: input
    id: start
    attributes:
      label: Start (Berlin time)
      description: Date and time in Berlin time, for example 2026-10-05T19:00.
      placeholder: "2026-10-05T19:00"
    validations:
      required: true
  - type: input
    id: end
    attributes:
      label: End (optional)
      placeholder: "2026-10-05T22:00"
  - type: input
    id: venue
    attributes:
      label: Venue
      placeholder: "Herrngarten"
  - type: input
    id: address
    attributes:
      label: Address
      placeholder: "Herrngarten, 64289 Darmstadt"
  - type: textarea
    id: description
    attributes:
      label: Description / event text
      render: markdown
  - type: dropdown
    id: free
    attributes:
      label: Admission
      default: Unknown
      options:
        - Unknown
        - Free
        - Paid
  - type: input
    id: price
    attributes:
      label: Price / admission details
  - type: input
    id: source_url
    attributes:
      label: Link / announcement URL
      placeholder: "https://…"
  - type: markdown
    attributes:
      value: >-
        After creating the issue you can drag &amp; drop a poster image
        into a comment. Thanks for sharing!
```

Keep the `label:` values exactly as written: the importer maps issue-form section headings (`### Event title`, `### Start (Berlin time)`, `### End (optional)`, `### Venue`, `### Address`, `### Description / event text`, `### Admission`, `### Price / admission details`, `### Link / announcement URL`) to fields.

- [ ] **Step 2: Verify the form is valid**

Run: `git add .github/ISSUE_TEMPLATE/event-share.yml && git commit -m "feat: add share-an-event issue template"`

Local verification of YAML structure only (GitHub renders the form):

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('.github/ISSUE_TEMPLATE/event-share.yml')); print('valid yaml')"
```

Expected: `valid yaml` (requires PyYAML; if unavailable, skip this check — the file is standard issue-form YAML).

- [ ] **Step 3: Commit**

```bash
git add .github/ISSUE_TEMPLATE/event-share.yml
git commit -m "feat: add share-an-event issue template"
```

### Task 2: Shared manual-submission module

Extracts the endpoint's validation/insert so the CLI can reuse it without importing `app.main` (which creates an app as a side effect).

**Files:**
- Create: `app/submissions.py`
- Modify: `app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `class SubmissionError(ValueError)`: user-facing rejection with a plain message.
- `validate_publication(event) -> None`: same checks as `app/main.py:79` but raises `SubmissionError`.
- `store_poster(db, data: bytes, extension: '.png'|'.jpg') -> str`: writes a poster file under `db.path.parent/'posters'` and returns `/api/posters/<uuid><extension>`.
- `submit_manual(db, fields: dict, poster_data=None, poster_ext=None)` -> dict: builds, validates, and stores one manual submission in the review queue; returns the stored event dict; raises `SubmissionError`. Accepts `poster_data` as either a `data:` URI string (web) or raw bytes (CLI, with `poster_ext`).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api.py`:

```python
from app.submissions import SubmissionError, submit_manual


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api.py -x -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.submissions'`

- [ ] **Step 3: Create `app/submissions.py`**

```python
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
    return db.event(eid)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api.py -x -q`
Expected: the two new tests PASS. (`test_submit_manual_accepts_raw_poster_bytes` writes to `db.path.parent/'posters'`, which is a temp dir, so no repo pollution.)

- [ ] **Step 5: Refactor `app/main.py` to use the shared module**

Replace the `validate_publication` definition (`app/main.py:79-87`) and its `HTTPException` version, then rewrite the submission and edit endpoints.

At the top of `app/main.py`, extend the import:

```python
from .submissions import SubmissionError, validate_publication
```

Delete the body of `validate_publication` in `main.py` (keep the name as a re-export via the import above; remove the `HTTPException`-raising definition entirely).

Replace the submission endpoint (`app/main.py:159-187`) with:

```python
    @app.post('/api/submissions', status_code=201)
    def submission(payload: EventInput):
        try:
            return submit_manual(db, payload.model_dump(exclude_unset=True))
        except SubmissionError as exc:
            raise HTTPException(422, str(exc))
```

Add the `submit_manual` import to the `app.main` import block:

```python
from .submissions import SubmissionError, submit_manual, validate_publication
```

Wrap the `edit` endpoint's validation so the new exception type maps to HTTP 422. In `app/main.py` `edit` (currently `app/main.py:198-211`), change:

```python
        validate_publication(event | changes)
```

to:

```python
        try:
            validate_publication(event | changes)
        except SubmissionError as exc:
            raise HTTPException(422, str(exc))
```

- [ ] **Step 6: Run the full Python suite**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q`
Expected: all existing tests PASS (the 422 status codes are preserved by the `except SubmissionError` conversion).

- [ ] **Step 7: Commit**

```bash
git add app/submissions.py app/main.py tests/test_api.py
git commit -m "refactor: share manual submission pipeline with importer"
```

### Task 3: Issue-body parser

**Files:**
- Create: `app/import_issues.py`
- Create: `tests/test_import_issues.py`

**Interface:**
- `parse_issue_body(body: str, heading_map: dict[str, str] | None = None) -> dict` maps issue-form markdown section headings to field keys. Admission (`Free`/`Paid`/`Unknown`) becomes `free: True/False/None`; blank sections are omitted; `Unknown` admission is omitted.

- [ ] **Step 1: Write the failing parser test**

Create `tests/test_import_issues.py`:

```python
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
```

- [ ] **Step 2: Run parser tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_import_issues.py -x -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.import_issues'`

- [ ] **Step 3: Implement `parse_issue_body`**

Create `app/import_issues.py`:

```python
"""Import open Submission issues from the GitHub repo into the local review queue."""
import json
import re
import subprocess
import sys
from pathlib import Path

from .db import Database
from .network import fetch as public_fetch
from .submissions import SubmissionError, submit_manual

HEADING_MAP = {
    'Event title': 'title',
    'Start (Berlin time)': 'start',
    'End (optional)': 'end',
    'Venue': 'venue',
    'Address': 'address',
    'Description / event text': 'description',
    'Admission': 'free',
    'Price / admission details': 'price',
    'Link / announcement URL': 'source_url',
}
ADMISSION = {'Free': True, 'Paid': False, 'Unknown': None}
IMAGE_PATTERN = re.compile(r'!\[[^\]]*\]\((https://[^)]+)\)')


def parse_issue_body(body, heading_map=None, admission=ADMISSION):
    heading_map = heading_map or HEADING_MAP
    sections = {}
    current = None
    for line in (body or '').splitlines():
        if line.startswith('### '):
            current = line[4:].strip()
            sections.setdefault(current, [])
        elif current is not None and line.strip():
            sections[current].append(line.strip())
    fields = {}
    for heading, key in heading_map.items():
        value = '\n'.join(sections.get(heading, [])).strip()
        if not value:
            continue
        if key == 'free':
            resolved = admission.get(value)
            if resolved is not None:
                fields['free'] = resolved
        else:
            fields[key] = value
    return fields
```

- [ ] **Step 4: Run parser tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_import_issues.py -x -q`
Expected: both parser tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/import_issues.py tests/test_import_issues.py
git commit -m "feat: parse share-an-event issue bodies"
```

### Task 4: Issue importer (fetch, store, label)

**Files:**
- Modify: `app/import_issues.py`
- Modify: `tests/test_import_issues.py`

**Interfaces:**
- `default_repo()` -> str: reads `owner/name` from `git remote get-url origin`.
- `gh(args: list[str])`: runs `gh` with JSON output and returns the parsed result.
- `fetch_issues(repo) -> list[dict]`: `gh issue list --label submission --state open --json number,title,body,labels,url,comments`.
- `_poster(issue) -> tuple[bytes | None, str | None]`: finds the first drag-dropped image URL in the issue or comment bodies, downloads it, and returns `(png_bytes, '.png')` / `(jpeg_bytes, '.jpg')`, or `(None, None)` if none is present or download/validation fails.
- `import_issue(db, repo, issue, apply=False) -> tuple[dict | None, str]`: skips issues already labeled `imported`; parses body; on `apply=False` returns `({...fields}, 'would import')`; on `apply=True` stores via `submit_manual`, labels `imported`, comments, and returns `(event, 'imported')`; on `SubmissionError` comments the error and returns `(None, 'error: ...')`.
- `main(repo=None, apply=False, db=None) -> int`: iterates open issues, prints one line each, returns the count.

- [ ] **Step 1: Write the failing importer test**

Append to `tests/test_import_issues.py`:

```python
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
    assert any('-add-label' in c and 'imported' in c for c in joins)
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
```

- [ ] **Step 2: Run importer tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_import_issues.py -x -q`
Expected: FAIL with `ImportError: cannot import name 'fetch_issues'`.

- [ ] **Step 3: Implement the importer**

Append to `app/import_issues.py`:

```python
def default_repo():
    origin = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout.strip()
    match = re.search(r'(?:github\.com[:/])([^/]+)/([^/.]+)', origin)
    if not match:
        raise SystemExit('Could not determine the GitHub repo from the git remote')
    return f'{match.group(1)}/{match.group(2)}'


def gh(args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit('gh failed: ' + result.stderr.strip())
    return json.loads(result.stdout)


def fetch_issues(repo):
    return gh(['issue', 'list', '--repo', repo, '--label', 'submission', '--state', 'open',
               '--json', 'number,title,body,labels,url,comments'])


def _poster(issue):
    text = issue.get('body') or ''
    for comment in issue.get('comments') or []:
        text += '\n' + (comment.get('body') or '')
    for url in IMAGE_PATTERN.findall(text):
        try:
            data = public_fetch(url)
        except Exception:
            continue
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            return data, '.png'
        if data.startswith(b'\xff\xd8\xff'):
            return data, '.jpg'
    return None, None


def import_issue(db, repo, issue, apply=False):
    if any(label.get('name') == 'imported' for label in issue.get('labels') or []):
        return None, 'skipped (already imported)'
    fields = parse_issue_body(issue['body'])
    if not fields.get('title'):
        return None, 'missing title'
    if not apply:
        return fields, 'would import'
    try:
        poster_data, poster_ext = _poster(issue)
        event = submit_manual(db, fields, poster_data=poster_data,
                              poster_ext=poster_ext or ('.png' if poster_data else None))
        gh(['issue', 'edit', str(issue['number']), '--repo', repo, '--add-label', 'imported'])
        gh(['issue', 'comment', str(issue['number']), '--repo', repo,
            '--body', 'Imported into the local review queue.'])
        return event, 'imported'
    except SubmissionError as exc:
        gh(['issue', 'comment', str(issue['number']), '--repo', repo,
            '--body', f'Could not import: {exc}'])
        return None, f'error: {exc}'


def main(repo=None, apply=False, db=None):
    repo = repo or default_repo()
    db = db or Database()
    issues = fetch_issues(repo)
    count = 0
    for issue in issues:
        _, note = import_issue(db, repo, issue, apply=apply)
        print(f'#{issue["number"]}: {note}')
        if not note.startswith('skipped') and note != 'would import':
            count += 1
    return count


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Import Submission issues into the review queue')
    parser.add_argument('--repo', default=None, help='owner/name (default: git remote origin)')
    parser.add_argument('--import', dest='apply', action='store_true', help='actually import (default: dry run)')
    args = parser.parse_args()
    sys.exit(main(repo=args.repo, apply=args.apply))
```

- [ ] **Step 4: Run importer tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_import_issues.py -x -q`
Expected: all four importer tests PASS. Verify no other module imports `app.import_issues` (importing it must not create a database — it does not; `Database()` is only instantiated in `main()`).

- [ ] **Step 5: Verify the CLI help works**

Run: `PYTHONPATH=. .venv/bin/python -m app.import_issues --help`
Expected: prints the help text, exits 0. Do not run the real import (no network/`gh` in tests).

- [ ] **Step 6: Commit**

```bash
git add app/import_issues.py tests/test_import_issues.py
git commit -m "feat: import submission issues into the review queue"
```

### Task 5: `POST /api/push` endpoint

**Files:**
- Modify: `app/db.py`
- Modify: `app/main.py`
- Modify: `tests/test_api.py`

**Interface:**
- `Database.checkpoint() -> None`: runs `PRAGMA wal_checkpoint(TRUNCATE)`, reads the result row, and raises `RuntimeError` if the checkpoint reports busy (`row[0] != 0`) — otherwise a stale DB snapshot could be committed.
- `POST /api/push` -> dict: checkpoints the DB (any error → HTTP 409); resolves the branch via `git rev-parse --abbrev-ref HEAD` (failure → 500); force-adds `data/events.sqlite` (`git add -f`, so it works even while `data/` is ignored — see note below); if `git diff --cached --quiet -- data/events.sqlite` reports no staged change AND HEAD is not ahead of `origin/<branch>`, returns `{'status': 'unchanged'}`; otherwise commits `git commit --only -m "events: publish review state" -- data/events.sqlite` (scoped so unrelated staged WIP is never swept in), does `git push origin <branch>`, and returns `{'status': 'pushed', 'branch': '<name>'}`. Any git failure → HTTP 500 with the git stderr.
- The ahead-of-origin check makes the endpoint self-healing: after a push failure that left a local commit unpushed, the next call pushes the pending commit instead of reporting `unchanged`.

**Design note (why this is not status/porcelain based):** `data/` is gitignored and `data/events.sqlite` starts untracked, so `git status --porcelain -- data/events.sqlite` prints nothing for an ignored file and a plain `git add` refuses it. Change-detection therefore uses `git add -f` + `git diff --cached --quiet`; `-f` is harmless once the file is tracked.

- [ ] **Step 1: Write the failing `/api/push` tests**

Append to `tests/test_api.py` (replacing any older FakeGit-based push tests):

```python
import subprocess


class FakeGit:
    def __init__(self, staged_changed=True, remote_sync=True, fail=None):
        self.staged_changed = staged_changed
        self.remote_sync = remote_sync
        self.fail = fail
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        if self.fail:
            cmd = argv[3] if len(argv) > 3 and argv[1] == '-C' else argv[0]
            if cmd in self.fail:
                return subprocess.CompletedProcess(argv, 1, stdout='', stderr='boom')
        try:
            cmd = argv[3] if len(argv) > 3 and argv[1] == '-C' else argv[0]
        except IndexError:
            cmd = argv[0]
        if cmd == 'rev-parse' and '--abbrev-ref' in argv:
            return subprocess.CompletedProcess(argv, 0, stdout='main\n')
        if cmd == 'rev-parse' and '--verify' in argv:
            if not self.remote_sync:
                return subprocess.CompletedProcess(argv, 1, stdout='')
            return subprocess.CompletedProcess(argv, 0, stdout='abc123\n')
        if cmd == 'rev-parse':
            return subprocess.CompletedProcess(argv, 0, stdout='abc123\n')
        if cmd == 'diff':
            return subprocess.CompletedProcess(argv, 0 if not self.staged_changed else 1, stdout='')
        return subprocess.CompletedProcess(argv, 0, stdout='')


def test_push_returns_unchanged_when_no_local_change(tmp_path, monkeypatch):
    fake = FakeGit(staged_changed=False, remote_sync=True)
    monkeypatch.setattr('app.main.subprocess.run', fake.run)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        assert client.post('/api/push').json() == {'status': 'unchanged'}
    assert any('-f' in c and 'data/events.sqlite' in c for c in fake.calls)
    assert any('diff' in c and '--cached' in c for c in fake.calls)


def test_push_stages_only_db_commits_scoped_and_pushes(tmp_path, monkeypatch):
    fake = FakeGit(staged_changed=True, remote_sync=True)
    monkeypatch.setattr('app.main.subprocess.run', fake.run)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        result = client.post('/api/push').json()
    assert result['status'] == 'pushed'
    assert result['branch'] == 'main'
    adds = [c for c in fake.calls if 'add' in c]
    assert adds and all('-f' in c and 'data/events.sqlite' in c for c in adds)
    commits = [c for c in fake.calls if 'commit' in c]
    assert commits and all('--only' in c and 'data/events.sqlite' in c and 'events: publish review state' in ' '.join(c) for c in commits)
    assert any('push' in c and 'origin' in c and 'main' in c for c in fake.calls)
    assert not any('-wal' in ' '.join(c) for c in fake.calls)


def test_push_retries_when_ahead_of_remote_without_commit(tmp_path, monkeypatch):
    fake = FakeGit(staged_changed=False, remote_sync=False)
    monkeypatch.setattr('app.main.subprocess.run', fake.run)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        result = client.post('/api/push').json()
    assert result['status'] == 'pushed'
    assert result['branch'] == 'main'
    assert not any('commit' in c for c in fake.calls)
    assert any('push' in c for c in fake.calls)


def test_push_failure_returns_500(tmp_path, monkeypatch):
    fake = FakeGit(staged_changed=True, remote_sync=True, fail=['add'])
    monkeypatch.setattr('app.main.subprocess.run', fake.run)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        response = client.post('/api/push')
    assert response.status_code == 500


def test_push_busy_database_returns_409(tmp_path, monkeypatch):
    def boom(db):
        raise RuntimeError('busy')
    monkeypatch.setattr('app.main.Database.checkpoint', boom)
    with TestClient(create_app(Database(tmp_path / 'events.sqlite'), scheduling=False)) as client:
        response = client.post('/api/push')
    assert response.status_code == 409


def test_push_integration_real_git(tmp_path, monkeypatch):
    origin = tmp_path / 'origin.git'
    subprocess.run(['git', 'init', '--bare', str(origin)], check=True, capture_output=True)
    work = tmp_path / 'work'
    subprocess.run(['git', 'init', str(work)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'config', 'user.email', 't@example.com'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'config', 'user.name', 'Test'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'remote', 'add', 'origin', str(origin)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'commit', '--allow-empty', '-m', 'init'], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(work), 'push', '-u', 'origin', 'HEAD'], check=True, capture_output=True)
    data = work / 'data'
    data.mkdir()
    (data / 'events.sqlite').write_bytes(b'hello')
    monkeypatch.setattr('app.main.ROOT', work)
    with TestClient(create_app(Database(tmp_path / 'db.sqlite'), scheduling=False)) as client:
        first = client.post('/api/push').json()
        second = client.post('/api/push').json()
    assert first['status'] == 'pushed'
    assert second == {'status': 'unchanged'}
    branch = first['branch']
    files = subprocess.run(['git', '-C', str(work), 'ls-files'], capture_output=True, text=True).stdout.split()
    assert files == ['data/events.sqlite']
    remote_head = subprocess.run(['git', '-C', str(work), 'rev-parse', 'origin/' + branch],
                                 capture_output=True, text=True).stdout.strip()
    local_head = subprocess.run(['git', '-C', str(work), 'rev-parse', 'HEAD'],
                                capture_output=True, text=True).stdout.strip()
    assert remote_head == local_head
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api.py -x -q`
Expected: FAIL with `404 Client Error` in `TestClient` for `/api/push`.

- [ ] **Step 3: Add `Database.checkpoint`**

In `app/db.py`, directly after `set_meta` (`app/db.py:63-65`), add:

```python
    def checkpoint(self):
        with self.connect() as con:
            row = con.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if row is not None and row[0] != 0:
                raise RuntimeError('database busy during checkpoint')
```

- [ ] **Step 4: Add the push endpoint**

At the top of `app/main.py`, add `import subprocess` to the imports (after `import os`, keeping alphabetical order):

```python
import os
import subprocess
```

Import `ROOT` already exists (`from .db import Database, ROOT`). The `local_guard` middleware currently returns 415 for any non-`/api/collect` POST without a JSON body — extend its exemption tuple to `('/api/collect', '/api/push')` so the body-less push request reaches the endpoint (same-origin/CSRF protection still applies). After the `@app.post('/api/collect' ...)` block (`app/main.py:157`), add:

```python
    @app.post('/api/push')
    def push():
        try:
            db.checkpoint()
        except Exception as exc:
            raise HTTPException(409, 'Database is busy; try again: ' + str(exc))
        git_root = str(ROOT)
        def git(args):
            return subprocess.run(['git', '-C', git_root, *args], capture_output=True, text=True)
        branch_run = git(['rev-parse', '--abbrev-ref', 'HEAD'])
        if branch_run.returncode or not branch_run.stdout.strip():
            raise HTTPException(500, branch_run.stderr.strip() or 'could not determine branch')
        branch = branch_run.stdout.strip()
        add = git(['add', '-f', 'data/events.sqlite'])
        if add.returncode:
            raise HTTPException(500, add.stderr.strip() or 'git add failed')
        staged = git(['diff', '--cached', '--quiet', '--', 'data/events.sqlite'])
        local = git(['rev-parse', 'HEAD'])
        remote = git(['rev-parse', '--verify', '--quiet', 'origin/' + branch])
        ahead = remote.returncode != 0 or (remote.stdout.strip() and remote.stdout.strip() != local.stdout.strip())
        if staged.returncode == 0 and not ahead:
            return {'status': 'unchanged'}
        if staged.returncode != 0:
            commit = git(['commit', '--only', '-m', 'events: publish review state', '--', 'data/events.sqlite'])
            if commit.returncode:
                raise HTTPException(500, commit.stderr.strip() or 'git commit failed')
        push = git(['push', 'origin', branch])
        if push.returncode:
            raise HTTPException(500, push.stderr.strip() or 'git push failed')
        return {'status': 'pushed', 'branch': branch}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `PYTHONPATH=. .venv/bin/python -m pytest tests/test_api.py -x -q`
Expected: all pass, including the real-git integration test (scratch bare origin in `tmp_path`; no network, never touches the real remote). `app.main` module-level `app = create_app()` creates the real repo DB during import; the FakeGit tests monkeypatch `subprocess.run` so no real git runs against it.

- [ ] **Step 6: Run the full Python suite**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/db.py app/main.py tests/test_api.py
git commit -m "feat: publish and push the reviewed database"
```

### Task 6: Editor-mode frontend

**Files:**
- Create: `web/src/vite-env.d.ts`
- Modify: `web/src/main.tsx`
- Modify: `web/src/i18n.mjs`

**Interface:**
- `const EDITOR = import.meta.env.VITE_EDITOR === "1"` — when true, only Review and Admin tabs render, the Share button and Sources/Discover tabs are hidden, and the initial tab is `review`.

- [ ] **Step 1: Write editor-mode i18n copy**

In `web/src/i18n.mjs`, inside the `en` dictionary after `"admin.showing"` (`web/src/i18n.mjs:153`) add:

```js
    "admin.editor": "Editor mode",
    "admin.publish": "Publish & push to GitHub",
    "admin.publishing": "Pushing…",
    "admin.pushed": "Review state pushed to GitHub.",
    "admin.pushUnchanged": "Nothing to publish — the database is unchanged.",
    "admin.pushFailed": "Push failed:",
```

Inside the `de` dictionary after the matching `"admin.showing"` (`web/src/i18n.mjs:320`) add:

```js
    "admin.editor": "Redaktionsmodus",
    "admin.publish": "Veröffentlichen & auf GitHub pushen",
    "admin.publishing": "Wird gepusht …",
    "admin.pushed": "Prüfstand nach GitHub gepusht.",
    "admin.pushUnchanged": "Nichts zu veröffentlichen – die Datenbank ist unverändert.",
    "admin.pushFailed": "Push fehlgeschlagen:",
```

- [ ] **Step 2: Verify i18n keys**

Run: `cd web && npm test`
Expected: existing i18n tests still PASS.

- [ ] **Step 3: Add Vite env types**

Create `web/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />
```

- [ ] **Step 4: Editor flag, tab filter, and hidden controls**

In `web/src/main.tsx`, add the flag near the top after the imports (after line 21):

```ts
const EDITOR = import.meta.env.VITE_EDITOR === "1";
```

Change the initial tab in `App` (`web/src/main.tsx:685`) from:

```ts
  const [tab, setTab] = useState("discover"),
```

to:

```ts
  const [tab, setTab] = useState(EDITOR ? "review" : "discover"),
```

Wrap the Discover and Sources nav buttons (`web/src/main.tsx:859-871`) so they only render in public mode:

```tsx
          {!EDITOR && (
            <button
              className={tab === "discover" ? "active" : ""}
              onClick={() => setTab("discover")}
            >
              {tr("nav.discover")}
            </button>
          )}
          {!EDITOR && (
            <button
              className={tab === "sources" ? "active" : ""}
              onClick={() => setTab("sources")}
            >
              {tr("nav.sources")}
            </button>
          )}
```

Hide the Share button in editor mode (`web/src/main.tsx:885-890`):

```tsx
        {!EDITOR && (
          <button
            className="header-contribute"
            onClick={() => setContribute(true)}
          >
            ＋ {tr("header.share")}
          </button>
        )}
```

- [ ] **Step 5: Type-check and build the editor variant**

Run: `cd web && npm run build` and `cd web && VITE_EDITOR=1 npm run build`
Expected: both complete with no TypeScript errors (`tsc -b` passes; Vite emits `web/dist`). Verify the editor build itself is valid by checking the dist emitted without error.

- [ ] **Step 6: Commit**

```bash
git add web/src/vite-env.d.ts web/src/i18n.mjs web/src/main.tsx
git commit -m "feat: editor-mode build showing only review and admin"
```

Note: `web/src/main.tsx` already had uncommitted changes before this task; only the editor-mode lines are part of this plan, and the commit above stages the file state after both sets of edits. Do not `git add -A` anywhere in this plan.

### Task 7: Publish & push button in the editor Admin view

**Files:**
- Modify: `web/src/main.tsx`
- Modify: `web/src/i18n.mjs`

- [ ] **Step 1: Add push state and handler**

In `App`, after the `suggest` state (`web/src/main.tsx:714`), add:

```tsx
  const [pushing, setPushing] = useState(false),
    [pushNote, setPushNote] = useState("");
```

In `App`, after the `mutate` function (`web/src/main.tsx:833`), add:

```tsx
  async function pushReview() {
    setPushing(true);
    setPushNote("");
    try {
      const result = (await api("/push", "POST")) as { status: string };
      setPushNote(
        result.status === "pushed"
          ? tr("admin.pushed")
          : tr("admin.pushUnchanged"),
      );
      await refresh();
    } catch (err) {
      setNotice(`${tr("admin.pushFailed")} ${(err as Error).message}`);
    } finally {
      setPushing(false);
    }
  }
```

- [ ] **Step 2: Render the button in the Admin workspace**

In the admin workspace section (`web/src/main.tsx:1442-1445`), replace:

```tsx
            <p className="eyebrow">{tr("review.eyebrow")}</p>
            <h1>{tr("admin.heading")}</h1>
            <p className="intro">{tr("admin.intro")}</p>
```

with:

```tsx
            <p className="eyebrow">
              {tr("review.eyebrow")} · {tr("admin.editor")}
            </p>
            <h1>{tr("admin.heading")}</h1>
            <p className="intro">{tr("admin.intro")}</p>
            {EDITOR && (
              <p className="collection-panel">
                <button
                  className="primary"
                  disabled={pushing}
                  onClick={pushReview}
                >
                  {pushing ? tr("admin.publishing") : tr("admin.publish")}
                </button>
                {pushNote && <span className="muted"> {pushNote}</span>}
              </p>
            )}
```

- [ ] **Step 3: Type-check and build**

Run: `cd web && VITE_EDITOR=1 npm run build`
Expected: no TypeScript errors; Vite build completes.

- [ ] **Step 4: Commit**

```bash
git add web/src/main.tsx web/src/i18n.mjs
git commit -m "feat: publish & push button in editor admin view"
```

### Task 8: `run.sh` editor mode

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Build editor variant when flagged**

Replace `run.sh` line 14:

```bash
(cd web && npm run build)
```

with:

```bash
if [[ "${MODE:-}" == "editor" || "${DARMSTADT_MODE:-}" == "editor" ]]; then
  export DARMSTADT_MODE=editor
  (cd web && VITE_EDITOR=1 npm run build)
else
  (cd web && npm run build)
fi
```

- [ ] **Step 2: Verify the script parses**

Run: `bash -n run.sh`
Expected: exit 0, no output.

- [ ] **Step 3: Commit**

```bash
git add run.sh
git commit -m "feat: run local editor mode with MODE=editor"
```

### Task 9: Track the database; un-ignore it

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Un-ignore `data/events.sqlite`**

Replace the `data/` line in `.gitignore` (`data/` at line 4) with:

```gitignore
data/*
!data/events.sqlite
```

This keeps `events.sqlite-shm`, `events.sqlite-wal`, and `data/posters/` ignored while tracking the DB file itself.

- [ ] **Step 2: Verify gitignore behavior**

Run: `git check-ignore data/events.sqlite-shm data/events.sqlite-wal; echo "wal/shm exit: $?"` and `git check-ignore data/events.sqlite || echo "events.sqlite NOT ignored"`
Expected: the first command ignores WAL/SHM (exit 0 lines), the second prints `events.sqlite NOT ignored`.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: track the events database"
```

### Task 10: README documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the new workflows**

Append to `README.md` at the end of the "Storage and development" section:

```markdown
### Editor mode and GitHub issues

Run `MODE=editor ./run.sh` to start the local editorial desk with only the Review and Admin views; the Admin view includes a **Publish & push** control that mints a commit and pushes `data/events.sqlite` to the repo. The database is tracked; its WAL sidecar files and `data/posters/` remain ignored.

Visitors share events by opening the **Share an event** issue template on the GitHub repo (issues labeled `submission`). Import those into the local review queue with:

```sh
PYTHONPATH=. .venv/bin/python -m app.import_issues        # dry run
PYTHONPATH=. .venv/bin/python -m app.import_issues --import
```

Each issue becomes a review-queue event with provenance pointing at the issue; a poster dragged into an issue comment is stored as reference material. Imported issues get the `imported` label and a confirmation comment; invalid submissions receive an explanation on the issue.
```

- [ ] **Step 2: Review**

Read the modified `README.md` section: confirm the commands, the tracked-DB statement, and the label/comment behavior match the implementation.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document editor mode, push, and issue intake"
```

### Task 11: End-to-end verification

- [ ] **Step 1: Full Python suite**

Run: `PYTHONPATH=. .venv/bin/python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Full frontend suite and builds**

Run: `cd web && npm test && npm run build && VITE_EDITOR=1 npm run build`
Expected: tests pass; both builds complete without errors.

- [ ] **Step 3: Manual smoke of the editor**

Run: `MODE=editor ./run.sh`, open http://127.0.0.1:8765.
Expected: only Review and Admin tabs render; no Share button or Discover/Sources navigation; Admin shows the "Publish & push to GitHub" control.

- [ ] **Step 4: Manual smoke of the public build**

Run: `./run.sh`, open http://127.0.0.1:8765.
Expected: normal public UI with all four tabs and the Share button.

- [ ] **Step 5: Confirm the tracking muddle is clean**

Run: `git status --short`
Expected: no unexpected tracked database files; `data/events.sqlite` is either committed or clean.