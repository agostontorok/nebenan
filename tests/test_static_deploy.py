import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = 'scripts/build-static.sh'


def vercel_json():
    return json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))


def workflow():
    return (ROOT / '.github/workflows/pages.yml').read_text(encoding='utf-8')


def ignore_lines():
    return (ROOT / '.vercelignore').read_text(encoding='utf-8').splitlines()


def test_vercel_build_runs_the_shared_script():
    assert vercel_json()['buildCommand'] == f'bash {SCRIPT}'


def test_vercel_serves_the_static_build_output():
    assert vercel_json()['outputDirectory'] == 'web/dist'


def test_vercel_does_not_autodetect_a_python_runtime():
    # framework: null selects the "Other" preset. Without it Vercel reads
    # requirements.txt and tries to serve app.main:app.
    assert 'framework' in vercel_json()
    assert vercel_json()['framework'] is None


def test_vercel_skips_the_root_install():
    assert vercel_json()['installCommand'] == ''


def test_vercel_redirects_directory_paths_to_a_trailing_slash():
    # Vite builds with base "./", so the app fetches ./data.json relative to the
    # current URL. At /darmstadt that resolves to /data.json, which is not
    # deployed, and the page renders empty.
    assert vercel_json()['trailingSlash'] is True


def test_pages_workflow_builds_with_the_shared_script():
    assert f'run: bash {SCRIPT}' in workflow()


def test_pages_workflow_still_runs_the_test_suite():
    assert 'python -m pytest -q' in workflow()


def test_pages_workflow_still_uploads_the_build_output():
    assert 'path: web/dist' in workflow()


def test_deploy_inputs_are_not_excluded_from_the_upload():
    ignored = {line.strip() for line in ignore_lines()}
    assert 'data/events.sqlite' not in ignored
    assert '.vercelignore' not in ignored


def test_database_write_ahead_log_is_excluded_from_the_upload():
    # These are megabytes of uncommitted local state. SQLite recreates them.
    ignored = {line.strip() for line in ignore_lines()}
    assert 'data/events.sqlite-wal' in ignored
    assert 'data/events.sqlite-shm' in ignored


def test_ignore_file_covers_dependencies_and_caches():
    ignored = {line.strip() for line in ignore_lines()}
    assert {'.venv/', 'node_modules/', '__pycache__/', '.git/'} <= ignored


def test_build_script_exports_data_and_builds_the_frontend_read_only():
    script = (ROOT / SCRIPT).read_text(encoding='utf-8')
    assert 'app.export_static' in script
    assert re.search(r'VERSION=1\s+npm run build', script)
    assert 'set -euo pipefail' in script


def test_build_script_is_executable():
    assert (ROOT / SCRIPT).stat().st_mode & 0o111, f'{SCRIPT} is not executable'
