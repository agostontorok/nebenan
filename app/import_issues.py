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
    heading_map = heading_map if heading_map is not None else HEADING_MAP
    sections = {}
    current = None
    for line in (body or '').splitlines():
        if line.startswith('### '):
            label = line[4:].strip()
            if label in heading_map:
                current = label
                sections.setdefault(label, [])
                continue
        if current is not None and line.strip():
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
        return None, 'error: missing title'
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
