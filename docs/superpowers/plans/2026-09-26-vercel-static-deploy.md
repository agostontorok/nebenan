# Vercel Static Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing read-only static site to Vercel from a `scripts/build-static.sh` that GitHub Pages also calls, so both deploy targets stay in lockstep.

**Architecture:** One canonical shell script performs the three static-build steps (install Python deps, export the database to JSON, build the frontend with `VITE_STATIC=1`). `vercel.json` points Vercel's single build command at that script and serves `web/dist` as static output. `.github/workflows/pages.yml` calls the same script instead of its inline steps. No runtime component, no database access at request time, no new Python dependencies.

**Tech Stack:** Bash, Python 3.11+ (`app/export_static.py`), Node 20 + Vite (`web/`), Vercel (`vercel.json`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-26-vercel-static-deploy-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/build-static.sh` | create, `chmod +x` | The single definition of the static build. Installs `requirements.txt`, exports `data.json`, builds the frontend read-only. Called by Vercel and by GitHub Pages. |
| `vercel.json` | create | Tells Vercel to use the script, output `web/dist`, and not auto-detect a Python runtime. |
| `.vercelignore` | create | Keeps `.venv/`, `node_modules/`, WAL sidecars and other local state out of the deployment upload. |
| `tests/test_static_deploy.py` | create | Guards the deploy configuration: required `vercel.json` fields, that both deploy targets call the shared script, and that the ignore file does not exclude the database. |
| `.github/workflows/pages.yml` | modify | Replace four inline build steps with one call to the shared script. |
| `README.md` | modify | Add a "Deploying" section. |
| `app/`, `web/src/`, `run.sh` | untouched | Application behaviour does not change. |

## Task 1: Guard the deploy configuration with tests

Write the tests first. They fail, because none of the files exist yet.

**Files:**
- Create: `tests/test_static_deploy.py`

- [ ] **Step 1: Write the failing test file**

The repo root is two levels above `tests/`. PyYAML is not a project dependency, so the workflow is checked with targeted text assertions rather than a YAML parse; `vercel.json` is real JSON and is parsed properly.

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_static_deploy.py -q`
Expected: FAIL. `FileNotFoundError` on `vercel.json`, reported as errors during collection or as failures inside each test.

- [ ] **Step 3: Commit the tests**

```bash
git add tests/test_static_deploy.py
git commit -m "test: guard the static deploy configuration"
```

Do not push yet. These tests fail on purpose, and `pages.yml` runs `pytest` on every push. The first push happens in Task 7, after everything passes.

---

## Task 2: Create the shared build script

**Files:**
- Create: `scripts/build-static.sh`

- [ ] **Step 1: Create `scripts/` and write the script**

```bash
mkdir -p scripts
cat > scripts/build-static.sh <<'SCRIPT'
#!/usr/bin/env bash
# The single static build for both deploy targets: GitHub Pages and Vercel.
# Produces web/dist from the committed database. See
# docs/superpowers/specs/2026-09-26-vercel-static-deploy-design.md
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Python dependencies for the database export.
if python3 -m pip --version >/dev/null 2>&1; then
  python3 -m pip install --quiet -r requirements.txt
elif command -v uv >/dev/null 2>&1; then
  uv pip install --system -r requirements.txt
else
  echo "build-static: need pip or uv to install requirements.txt" >&2
  exit 1
fi

# 2. Export the database to the JSON the read-only frontend fetches.
PYTHONPATH=. python3 -m app.export_static

# 3. Build the frontend with VITE_STATIC=1, which hides every mutating view
#    and makes the app read data.json instead of calling the API.
cd web
npm ci
VITE_STATIC=1 npm run build
SCRIPT
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/build-static.sh
```

- [ ] **Step 3: Verify the script runs end to end locally**

Run: `bash scripts/build-static.sh`
Expected: exit code 0, ending with Vite's build summary. Confirm both artifacts exist:

```bash
ls -l web/dist/index.html web/dist/darmstadt/index.html web/dist/darmstadt/data.json
```

Expected: all three paths listed. `data.json` is roughly the size of the source database.

- [ ] **Step 4: Verify the build is read-only, not the local app**

The local build must not offer the Admin or Review surfaces. The review *data* still ships, because `app/export_static.py` includes it; `VITE_STATIC=1` is what keeps the editing UI out of the page. Confirm the payload shape:

```bash
.venv/bin/python -c "import json;d=json.load(open('web/dist/darmstadt/data.json'));print(sorted(d), len(d['review']))"
```

Expected: `['candidates', 'events', 'review', 'sources', 'status']` followed by an event count. Do not "fix" the JSON by removing `review`.

- [ ] **Step 5: Run the guard test for the script**

Run: `.venv/bin/python -m pytest tests/test_static_deploy.py -q -k build_script`
Expected: the four `build_script_*` tests PASS (`exports_the_database_to_json`, `builds_the_frontend_read_only`, `fails_fast`, `is_executable`); the rest still fail.

- [ ] **Step 6: Commit**

```bash
git add scripts/build-static.sh
git commit -m "build: shared static build script for Pages and Vercel"
```

---

## Task 3: Create the Vercel configuration

**Files:**
- Create: `vercel.json`

- [ ] **Step 1: Write `vercel.json`**

`framework: null` is the fix for the reported failure: it stops Vercel reading `requirements.txt` and trying to serve `app.main:app`, which is what raised the uv version error. `trailingSlash: true` is required, not cosmetic — see the test docstring.

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "framework": null,
  "installCommand": "",
  "buildCommand": "bash scripts/build-static.sh",
  "outputDirectory": "web/dist",
  "trailingSlash": true
}
```

- [ ] **Step 2: Validate the JSON**

Run: `.venv/bin/python -c "import json;print(json.load(open('vercel.json')))"`
Expected: the parsed dict, printed on one line, with `framework` as `None`.

- [ ] **Step 3: Run the guard tests**

Run: `.venv/bin/python -m pytest tests/test_static_deploy.py -q -k vercel`
Expected: all five `vercel_*` tests PASS.

- [ ] **Step 4: Commit**

```bash
git add vercel.json
git commit -m "build: Vercel static deployment config"
```

---

## Task 4: Create the upload ignore file

**Files:**
- Create: `.vercelignore`

- [ ] **Step 1: Write `.vercelignore`**

Patterns use gitignore syntax, so a bare `tests/` matches at any depth. `data/events.sqlite` is deliberately absent: the export reads it.

```
.venv/
.git/
.github/
__pycache__/
.pytest_cache/
node_modules/
data/events.sqlite-wal
data/events.sqlite-shm
data/posters/
docs/
tests/
run.sh
```

- [ ] **Step 2: Run the guard tests**

Run: `.venv/bin/python -m pytest tests/test_static_deploy.py -q -k ignore_file`
Expected: the three `ignore_file_*` tests PASS.

- [ ] **Step 3: Confirm the database is still uploaded**

Run: `.venv/bin/python -c "print('data/events.sqlite' in {l.strip() for l in open('.vercelignore')})"`
Expected: `False`, meaning no whole line in the ignore file names the database, so it is uploaded. Compare whole lines, not the raw file text: the sidecar lines `data/events.sqlite-wal` and `data/events.sqlite-shm` deliberately contain the substring `data/events.sqlite` and are expected to be present, so a substring check cannot distinguish them and would report `True` against a correct ignore file. That ambiguity is why the real guard is the pattern-matching test in Step 2.

- [ ] **Step 4: Commit**

```bash
git add .vercelignore
git commit -m "build: exclude local state from the Vercel upload"
```

---

## Task 5: Point the Pages workflow at the shared script

**Files:**
- Modify: `.github/workflows/pages.yml`

- [ ] **Step 1: Replace the four inline build steps**

In the `build` job, delete the steps `Install Python dependencies`, `Export static review state`, `Install frontend dependencies`, and `Build static site`. Keep `actions/checkout`, `actions/setup-python`, `Run tests`, `actions/setup-node`, and everything from `actions/configure-pages` onwards. The result is:

```yaml
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Run tests
        run: python -m pytest -q

      - uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Build static site
        run: bash scripts/build-static.sh

      - uses: actions/configure-pages@v5

      - uses: actions/upload-pages-artifact@v3
        with:
          path: web/dist
```

The `deploy` job is unchanged.

- [ ] **Step 2: Run the guard tests**

Run: `.venv/bin/python -m pytest tests/test_static_deploy.py -q -k pages`
Expected: all three `pages_*` tests PASS.

- [ ] **Step 3: Run the full Python suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests PASS, including the pre-existing suite.

- [ ] **Step 4: Run the frontend suite**

Run: `cd web && npm test`
Expected: PASS, no failures.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/pages.yml
git commit -m "ci: build Pages with the shared static build script"
```

---

## Task 6: Document the deployment

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the section**

Insert before the `## Storage and development` heading:

```markdown
## Deploying

The public site is static and read-only. It is built from the committed database by
`scripts/build-static.sh` and deployed to two targets: GitHub Pages and Vercel, both
triggered by a push to `main`. Vercel serves the custom domain.

`VITE_STATIC=1` makes the build read-only: the frontend fetches `data.json` instead of
calling the API, and Admin, Review, submissions and editing are absent. Those stay in the
local `./run.sh` server. Visitors submit events through the GitHub issue templates.

To refresh the live data, collect locally, then use **Publish & push** in the editor view.
The push checkpoints the SQLite write-ahead log before committing, so the committed
`events.sqlite` is self-contained. Committing `events.sqlite` without a checkpoint deploys
the older data, and the missing write-ahead log cannot be recovered afterwards.
```

- [ ] **Step 2: Verify the section reads correctly against the implementation**

Run: `grep -n "scripts/build-static.sh" README.md`
Expected: the new line, plus the existing reference in the storage section if present.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: describe the Vercel deployment"
```

---

## Task 7: Verify both build paths

Neither deploy target can be confirmed from the working tree, so both are exercised against the real services. Do not declare this task done on the strength of the local build alone.

**Files:** none

- [ ] **Step 1: Push the branch**

```bash
git push origin main
```

Expected: push succeeds. Two earlier commits (`d7b02f8`, `16de4a3`) go up with this push. Unrelated uncommitted work stays uncommitted and is not deployed.

- [ ] **Step 2: Verify build path 1, GitHub Pages**

```bash
gh run list --workflow pages.yml --limit 1
```

Expected: a run for the pushed commit with conclusion `success`. If it is `failure`, run `gh run view <id> --log-failed` and fix the cause before continuing — the shared script is what Pages uses, so a failure here is a real regression in the script, not a Pages-specific problem.

- [ ] **Step 3: Confirm the Pages artifact still serves the app**

```bash
gh api repos/agostontorok/nahe/pages --jq '.html_url'
```

Expected: the Pages URL. Then confirm its `/darmstadt/data.json` returns JSON. Substitute the current Pages base path, which includes the repository name, for `<base>`:

```bash
curl -sSf -o /dev/null -w '%{http_code}\n' "https://agostontorok.github.io/<base>/darmstadt/data.json"
```

Expected: `200`.

- [ ] **Step 4: Connect the repository to Vercel**

One-time. The CLI is already authenticated and `.vercel/project.json` already links the `nahe` project.

```bash
vercel git connect git@github.com:agostontorok/nahe.git
```

Expected: confirmation that the project is connected. If the GitHub App lacks repository access, authorise `nahe` at
`https://github.com/settings/installations` and re-run.

- [ ] **Step 5: Verify build path 2, Vercel**

```bash
vercel ls nahe
```

Expected: deployments listed, the newest from the commit pushed in Step 1 with a status of `READY`. If the build failed, read the log:

```bash
vercel inspect <deployment-url> --logs
```

The two failure modes to expect, in order of likelihood: the build image has neither `pip` nor `uv`, which the script reports as `build-static: need pip or uv...`; or the Python version cannot resolve the pinned `requirements.txt`. The first means falling back to the GitHub Actions approach in the spec, the second means adding a `.python-version`.

- [ ] **Step 6: Verify Vercel routing and read-only behaviour**

Set `HOST` to the production domain from the `vercel ls nahe` output, for example `nahe.vercel.app`:

```bash
HOST=nahe.vercel.app
```

Check the redirect that keeps the relative `data.json` fetch working:

```bash
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' "https://$HOST/darmstadt"
```

Expected: `308` with a `redirect_url` ending in `/darmstadt/`.

```bash
curl -sSf "https://$HOST/darmstadt/data.json" | .venv/bin/python -c "import json,sys;d=json.load(sys.stdin);print(sorted(d))"
```

Expected: `['candidates', 'events', 'review', 'sources', 'status']`.

```bash
curl -sSf "https://$HOST/darmstadt/" | grep -c "assets/"
```

Expected: a non-zero count, confirming the page and its bundle are served.

- [ ] **Step 7: Confirm no API call is attempted**

The page must not request `/api/*`. Confirm the relative fetch is what the bundle ships:

```bash
grep -rl 'data\.json' web/dist/assets/ | head
```

Expected: at least one match in the local build output. Then open `https://$HOST/darmstadt/` and confirm in the browser network panel that no request goes to `/api/`, that the event list and map render, and that no Admin or Review tab exists.

- [ ] **Step 8: Attach the custom domain**

A dashboard step, done only after Steps 5 to 7 are green. In the Vercel project, Settings → Domains → add the domain, then point the DNS record Vercel shows at the domain registrar. Confirm HTTPS provisions and the site loads on the custom host.

- [ ] **Step 9: Record the outcome**

Append the two verification results to the spec's Status line, so the next reader knows both paths were exercised:

```markdown
- **Status:** Approved (2026-09-26). Both build paths verified 2026-09-26.
```

```bash
git add docs/superpowers/specs/2026-09-26-vercel-static-deploy-design.md
git commit -m "docs: record verified deploy targets"
```
