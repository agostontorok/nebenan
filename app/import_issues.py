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