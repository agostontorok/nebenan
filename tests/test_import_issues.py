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