import fnmatch
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = 'scripts/build-static.sh'
SCRIPT_PATH = ROOT / SCRIPT


def vercel_config():
    return json.loads((ROOT / 'vercel.json').read_text(encoding='utf-8'))


def workflow_text():
    text = (ROOT / '.github/workflows/pages.yml').read_text(encoding='utf-8')
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('#'))


def ignored_patterns():
    return [line.strip()
            for line in (ROOT / '.vercelignore').read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.strip().startswith('#')]


def is_ignored(path):
    # A pattern containing a slash is anchored at the root; one without a
    # slash matches at any depth, as gitignore does.
    for pattern in ignored_patterns():
        pattern = pattern.rstrip('/')
        if '/' in pattern:
            if fnmatch.fnmatch(path, pattern) or path.startswith(pattern + '/'):
                return True
        elif any(fnmatch.fnmatch(part, pattern) for part in path.split('/')):
            return True
    return False


def build_script():
    return SCRIPT_PATH.read_text(encoding='utf-8')


def test_vercel_build_runs_the_shared_script():
    assert vercel_config()['buildCommand'] == f'bash {SCRIPT}'


def test_vercel_serves_the_static_build_output():
    assert vercel_config()['outputDirectory'] == 'web/dist'


def test_vercel_does_not_autodetect_a_python_runtime():
    config = vercel_config()
    # framework: null selects the "Other" preset. Without it Vercel reads
    # requirements.txt and tries to serve app.main:app.
    assert 'framework' in config
    assert config['framework'] is None


def test_vercel_skips_the_root_install():
    # An absent installCommand means the Vercel default, not an empty one.
    assert vercel_config()['installCommand'] == ''


def test_vercel_redirects_directory_paths_to_a_trailing_slash():
    # Vite builds with base "./", so the app fetches ./data.json relative to the
    # current URL. At /darmstadt that resolves to /data.json, which is not
    # deployed, and the page renders empty.
    assert vercel_config()['trailingSlash'] is True


def test_pages_workflow_builds_with_the_shared_script():
    assert f'bash {SCRIPT}' in workflow_text()


def test_pages_workflow_still_runs_the_test_suite():
    assert 'python -m pytest -q' in workflow_text()


def test_pages_workflow_still_uploads_the_build_output():
    assert 'path: web/dist' in workflow_text()


def test_ignore_file_does_not_exclude_the_committed_database():
    # The export reads this file. A pattern like data/ or *.sqlite would drop it
    # silently, so match patterns rather than comparing literal spellings.
    assert not is_ignored('data/events.sqlite')


def test_ignore_file_excludes_the_write_ahead_log_and_shared_memory():
    # These are megabytes of uncommitted local state. SQLite recreates them.
    assert is_ignored('data/events.sqlite-wal')
    assert is_ignored('data/events.sqlite-shm')


def test_ignore_file_does_not_exclude_the_source_registry():
    # app/db.py reads this registry while opening the database, so the static
    # export needs it. Excluding docs/ wholesale broke the first real Vercel
    # build with a FileNotFoundError; only the non-build subtrees are ignored.
    assert not is_ignored('docs/research/darmstadt-sources.json')
    assert is_ignored('docs/superpowers/plans/2026-09-26-vercel-static-deploy.md')


def test_ignore_file_covers_dependencies_caches_and_vcs_metadata():
    assert {'.venv/', 'node_modules/', '__pycache__/', '.git/'} <= set(ignored_patterns())


def test_build_script_exports_the_database_to_json():
    assert 'app.export_static' in build_script()


def test_build_script_builds_the_frontend_read_only():
    # A bare "npm run build" would ship the mutating Admin and Review views.
    assert re.search(r'^VITE_STATIC=1 npm run build', build_script(), re.M)


def test_build_script_fails_fast():
    assert 'set -euo pipefail' in build_script()


def test_build_script_is_executable():
    assert SCRIPT_PATH.stat().st_mode & 0o111, f'{SCRIPT} is not executable'
