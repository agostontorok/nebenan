# AI Reviewer Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local-only AI-review tab (EDITOR mode) that lists published `ai_extracted` events grouped by source, lets the operator step through them (fix/skip/mark-reviewed/hide), and — the core feature — after fixing a field on one event, offers to apply the same value to every other event in the same source that carries the identical old value.

**Architecture:** Reviewed state lives in a private `_ai_reviewed_at` override (never exported), surfaced by a local-only `GET /api/review/ai` endpoint. All queue/grouping/propagation logic is a pure client module (`ai-review.mjs`); propagation applies one small PATCH per affected event through the existing, server-validated `PATCH /api/events/{eid}`. The tab and its modal render only under `EDITOR && !STATIC`.

**Tech Stack:** FastAPI + SQLite (`app/`), React + Vite static site (`web/src/`), pytest (`tests/`), node:test + jest-style `*.test.mjs`, TypeScript via `tsc`.

**Working notes for every task:**
- Never stage `data/events.sqlite` (it is tracked — only commit with explicit paths, never `git add -A`).
- Dev server (PID 54820, `127.0.0.1:8765`) serves `web/dist/`; rebuild after web changes with `VITE_STATIC=1 npx vite build`.
- Frontend gates: `EDITOR = VITE_EDITOR === "1"`, `STATIC = VITE_STATIC === "1"`.

---

### Task 1: Backend — AI review endpoint + private reviewed-marker

**Files:**
- Modify: `app/db.py` — add `ai_events()` after `events()` (line ~137).
- Modify: `app/main.py` — `EventInput` field, `edit()` mapping, `GET /api/review/ai` route.
- Test: `tests/test_api.py`.

- [ ] **Step 1: Add the import and write the failing tests**

At the top of `tests/test_api.py`, add to the existing imports:

```python
from app.chat_ingest import ingest, ref_id, _event_id
```

Append to `tests/test_api.py`:

```python
def seed_ai_event(db, title, venue='Stadtbibliothek', start='2026-11-06T20:00', source='stadtbib'):
    ingest(db, [{
        'source': source,
        'page_url': 'https://programm.example/',
        'events': [{
            'title': title,
            'start': start,
            'venue': venue,
            'address': 'Grassweg 4, Darmstadt',
            'description': '',
            'url': 'https://programm.example/',
        }],
    }])


def test_ai_review_lists_only_published_ai_events(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    seed_ai_event(db, 'Konzert', venue='Stadthalle')
    from app.submissions import submit_manual
    submit_manual(db, {'title': 'Manuell', 'venue': 'Café', 'start': '2026-11-06T19:00:00+02:00'})
    with TestClient(create_app(db, scheduling=False)) as client:
        events = client.get('/api/review/ai').json()['events']
    assert len(events) == 1
    assert events[0]['title'] == 'Konzert'
    assert events[0]['ai_reviewed_at'] is None


def test_ai_reviewed_at_is_private_override(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    seed_ai_event(db, 'Konzert')
    with TestClient(create_app(db, scheduling=False)) as client:
        eid = client.get('/api/review/ai').json()['events'][0]['id']
        r = client.patch(f'/api/events/{eid}', json={'ai_reviewed_at': '2026-09-22T10:00:00+02:00'})
        assert r.status_code == 200
        reviewed = client.get('/api/review/ai').json()['events'][0]
        assert reviewed['ai_reviewed_at'] == '2026-09-22T10:00:00+02:00'
        published = client.get('/api/events').json()['events'][0]
        assert 'ai_reviewed_at' not in published
        assert '_ai_reviewed_at' not in published


def test_ai_hide_rejects_and_removes_from_public(tmp_path):
    db = Database(tmp_path / 'events.sqlite')
    seed_ai_event(db, 'Konzert')
    with TestClient(create_app(db, scheduling=False)) as client:
        eid = client.get('/api/review/ai').json()['events'][0]['id']
        r = client.patch(f'/api/events/{eid}', json={
            'status': 'rejected', 'review_reason': 'AI review: hidden',
            'ai_reviewed_at': '2026-09-22T10:00:00+02:00'})
        assert r.status_code == 200
        assert client.get('/api/events').json()['events'] == []
        assert client.get('/api/review/ai').json()['events'] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py -q -k ai_`
Expected: FAIL with `AttributeError: 'Database' object has no attribute 'ai_events'` and failing routes.

- [ ] **Step 3: Implement `db.ai_events()`**

Add to `app/db.py`, immediately after the `events()` method (after line 137):

```python
    def ai_events(self):
        """Published AI-extracted events with their private review marker.

        The marker is read from the `_ai_reviewed_at` override, which is
        stripped from effective data everywhere else, so live payloads never
        expose it.
        """
        with self.connect() as con:
            rows = con.execute('SELECT * FROM events').fetchall()
            names = self._source_names(con)
            provenance = {row['id']: [] for row in rows}
            for record in con.execute(
                    'SELECT source_id,external_id,event_id,url,checked_at,snapshot FROM refs ORDER BY checked_at DESC'):
                if record['event_id'] in provenance:
                    provenance[record['event_id']].append(self._provenance(record, names))
            result = []
            for row in rows:
                data = json.loads(row['data'])
                if data.get('status') != 'published' or not data.get('ai_extracted'):
                    continue
                overrides = json.loads(row['overrides'])
                event = self._event(row, names, provenance[row['id']])
                event['ai_reviewed_at'] = overrides.get('_ai_reviewed_at')
                result.append(event)
        return sorted(result, key=lambda e: e.get('start') or '9999')
```

- [ ] **Step 5: Add `ai_reviewed_at` to `EventInput` and map it in `edit()`**

In `app/main.py`, add the field to `EventInput` (after the `poster` field, ~line 30):

```python
    ai_reviewed_at: str | None = None
```

In `edit()` (line ~190), right after `changes = payload.model_dump(...)`, insert:

```python
        if 'ai_reviewed_at' in changes:
            changes['_ai_reviewed_at'] = changes.pop('ai_reviewed_at') or None
```

(This must run before `validate_publication` so the private key never reaches the merged event.)

- [ ] **Step 6: Add the `GET /api/review/ai` route**

In `app/main.py`, after the `/api/review` route (line ~124):

```python
    @app.get('/api/review/ai')
    def review_ai():
        return {'events': db.ai_events()}
```

- [ ] **Step 7: Run the full API suite**

Run: `.venv/bin/python -m pytest tests/test_api.py -q`
Expected: PASS, no regressions in the existing API tests.

- [ ] **Step 8: Commit**

```bash
git add app/db.py app/main.py tests/test_api.py
git commit -m "feat: local-only AI review endpoint and private reviewed marker"
```

---

### Task 2: Frontend pure module — group key + propagation candidates

**Files:**
- Create: `web/src/ai-review.mjs`
- Test: `web/src/ai-review.test.mjs`

- [ ] **Step 1: Write the failing tests** (create `web/src/ai-review.test.mjs`)

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { sourceGroup, propagationCandidates } from "./ai-review.mjs";

function aiEvent(id, overrides = {}) {
  return {
    id,
    title: `Event ${id}`,
    start: "2026-11-06T20:00",
    venue: "Stadthalle",
    address: "Darmstadt",
    status: "published",
    ai_extracted: true,
    ai_reviewed_at: null,
    provenance: [
      { source_id: "stadtbib", name: "Stadtbibliothek", url: "https://x.example/", checked_at: "" },
    ],
    ...overrides,
  };
}

test("sourceGroup uses the first source of provenance", () => {
  assert.deepEqual(sourceGroup(aiEvent("a")), { key: "stadtbib", label: "Stadtbibliothek" });
  assert.deepEqual(sourceGroup({ ...aiEvent("b"), provenance: [] }), {
    key: "manual",
    label: "Manual submission",
  });
});

test("venue fix proposes the other events sharing the old venue", () => {
  const original = aiEvent("a", { venue: "Stadthalle" });
  const events = [
    original,
    aiEvent("b", { venue: "Stadthalle" }),
    aiEvent("c", { venue: "Stadthalle" }),
    aiEvent("d", { venue: "Konzertsaal" }),
  ];
  const suggestions = propagationCandidates({ events, original, patch: { venue: "Stadthalle Darmstadt" } });
  assert.equal(suggestions.length, 1);
  assert.deepEqual(suggestions[0].matches.map((m) => m.id).sort(), ["b", "c"]);
  assert.equal(suggestions[0].newValue, "Stadthalle Darmstadt");
  assert.equal(suggestions[0].oldValue, "Stadthalle");
});

test("description and price changes never propagate", () => {
  const original = aiEvent("a", { description: "Alt", price: "5€" });
  const events = [original, aiEvent("b", { description: "Alt", price: "5€" })];
  assert.deepEqual(
    propagationCandidates({ events, original, patch: { description: "Neu", price: "8€" } }),
    [],
  );
});

test("title fixes propagate exact duplicates", () => {
  const original = aiEvent("a", { title: "Vortrag ✕" });
  const events = [original, aiEvent("b", { title: "Vortrag ✕" })];
  const suggestions = propagationCandidates({ events, original, patch: { title: "Vortrag" } });
  assert.equal(suggestions.length, 1);
  assert.deepEqual(suggestions[0].matches.map((m) => m.id), ["b"]);
});

test("start fixes match the same wall-clock time across formats", () => {
  const original = aiEvent("a", { start: "2026-11-06T20:00" });
  const events = [
    original,
    aiEvent("b", { start: "2026-11-06T20:00:00+01:00" }),
    aiEvent("c", { start: "2026-11-06T21:00" }),
  ];
  const suggestions = propagationCandidates({ events, original, patch: { start: "2026-11-06T19:00" } });
  assert.equal(suggestions.length, 1);
  assert.deepEqual(suggestions[0].matches.map((m) => m.id), ["b"]);
});

test("no suggestions when old value is empty or unique", () => {
  const a = aiEvent("a", { venue: "" });
  assert.deepEqual(propagationCandidates({ events: [a, aiEvent("b", { venue: "Stadthalle" })], original: a, patch: { venue: "Open Air" } }), []);
  const c = aiEvent("c", { venue: "Einzigartig" });
  assert.deepEqual(propagationCandidates({ events: [c, aiEvent("d", { venue: "Anders" })], original: c, patch: { venue: "Neu" } }), []);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd web && node --test src/ai-review.test.mjs`
Expected: FAIL — module `./ai-review.mjs` cannot be found.

- [ ] **Step 3: Implement `web/src/ai-review.mjs`**

```js
import { berlinInput } from "./event-patch.mjs";

export const PROPAGATION_FIELDS = ["venue", "address", "title", "start", "end"];

export function sourceGroup(event) {
  const source = event.provenance?.[0];
  return {
    key: source?.source_id ?? "manual",
    label: source?.name ?? "Manual submission",
  };
}

function normalized(field, value) {
  if (field === "start" || field === "end") return berlinInput(value);
  return value == null ? null : String(value);
}

export function propagationCandidates({ events, original, patch }) {
  const results = [];
  for (const field of PROPAGATION_FIELDS) {
    if (!(field in patch)) continue;
    const oldValue = normalized(field, original[field]);
    if (!oldValue) continue;
    const matches = events
      .filter((o) => o.id !== original.id)
      .filter((o) => normalized(field, o[field]) === oldValue)
      .map((o) => ({ id: o.id, title: o.title }));
    if (matches.length) results.push({ field, oldValue: original[field], newValue: patch[field], matches });
  }
  return results;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && node --test src/ai-review.test.mjs`
Expected: PASS, all six `ai-review` tests.

- [ ] **Step 5: Commit**

```bash
git add web/src/ai-review.mjs web/src/ai-review.test.mjs
git commit -m "feat: propagation candidates and source grouping for AI review"
```

---

### Task 3: i18n keys and coverage test

**Files:**
- Modify: `web/src/i18n.mjs` — English block (after `"review.defaultReason"`, ~line 185) and German block (after `"review.defaultReason"`, ~line 390).
- Modify: `web/src/i18n.test.mjs`.

- [ ] **Step 1: Add the English keys**

```js
    "ai.nav": "AI review",
    "ai.eyebrow": "LOCAL AI REVIEWER",
    "ai.title": "AI-extracted events.",
    "ai.intro": "Check what the local model captured before it stays published. Fixing a value offers to fix the same value on other events from the same source.",
    "ai.empty": "All AI events reviewed.",
    "ai.emptyCopy": "Nothing left in the queue.",
    "ai.reviewed": "Reviewed",
    "ai.needsReview": "Needs review",
    "ai.countReview": "{done} of {total} reviewed",
    "ai.auditLine": "Extracted by the local model",
    "ai.prev": "Previous",
    "ai.next": "Next",
    "ai.skip": "Skip",
    "ai.markReviewed": "Mark reviewed",
    "ai.hide": "Hide from public",
    "ai.hideConfirm": "Remove this event from the public site?",
    "ai.hidden": "Event hidden from the public site.",
    "ai.propagationTitle": "Same value on other events",
    "ai.propagationCopy": "{field} ›{old}‹ also appears on {n} other event(s) in this source — fix them all to ›{new}‹?",
```

- [ ] **Step 2: Add the German keys**

```js
    "ai.nav": "KI-Prüfung",
    "ai.eyebrow": "LOKALE KI-PRÜFUNG",
    "ai.title": "KI-extrahierte Termine.",
    "ai.intro": "Prüfe, was das lokale Modell erfasst hat, bevor es veröffentlicht bleibt. Korrigierst du einen Wert, bietet das Tool an, denselben Wert auf anderen Terminen derselben Quelle mitzukorrigieren.",
    "ai.empty": "Alle KI-Termine geprüft.",
    "ai.emptyCopy": "Nichts mehr in der Warteschlange.",
    "ai.reviewed": "Geprüft",
    "ai.needsReview": "Zu prüfen",
    "ai.countReview": "{done} von {total} geprüft",
    "ai.auditLine": "Vom lokalen Modell extrahiert",
    "ai.prev": "Zurück",
    "ai.next": "Weiter",
    "ai.skip": "Überspringen",
    "ai.markReviewed": "Als geprüft markieren",
    "ai.hide": "Vor Öffentlichkeit verbergen",
    "ai.hideConfirm": "Diesen Termin von der öffentlichen Seite entfernen?",
    "ai.hidden": "Termin vor der Öffentlichkeit verborgen.",
    "ai.propagationTitle": "Gleicher Wert auf weiteren Terminen",
    "ai.propagationCopy": "{field} ›{old}‹ steht auf {n} weiteren Terminen dieser Quelle — alle auf ›{new}‹ korrigieren?",
```

- [ ] **Step 3: Extend the coverage test**

In `web/src/i18n.test.mjs`, append the `ai.*` keys to the `for (const key of [...])` array in `test("English and German have complete navigation and filter copy", ...)`:

```js
    for (const key of ["nav.discover", "nav.sources", "nav.review", "nav.admin", "ai.nav", "ai.eyebrow", "ai.title", "ai.intro", "ai.empty", "ai.emptyCopy", "ai.reviewed", "ai.needsReview", "ai.countReview", "ai.auditLine", "ai.prev", "ai.next", "ai.skip", "ai.markReviewed", "ai.hide", "ai.hideConfirm", "ai.hidden", "ai.propagationTitle", "ai.propagationCopy", "filters.allTopics", "filters.allScales", "filters.freeOnly", "filters.semanticLoading", "filters.semanticReady", "filters.semanticFallback", "map.unknownLocation", "results.places", "results.placesDivider"]) {
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd web && node --test src/i18n.test.mjs`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/i18n.mjs web/src/i18n.test.mjs
git commit -m "feat: i18n copy for the local AI review flow"
```

---

### Task 4: `EventForm` reports the computed patch via `onSaved`

**Files:**
- Modify: `web/src/main.tsx` — `EventForm` props (`~383-387`) and `submit()` (`~433-438`).

- [ ] **Step 1: Add the `onSaved` prop to the signature**

At `main.tsx:383-387` change:

```tsx
}: {
  event?: EventItem;
  onDone: () => void;
  language: "en" | "de";
}) {
```

to:

```tsx
  onSaved,
}: {
  event?: EventItem;
  onDone: () => void;
  language: "en" | "de";
  onSaved?: (patch: Record<string, unknown>) => void | Promise<void>;
}) {
```

- [ ] **Step 2: Emit the patch after a successful save**

In `EventForm.submit()`, replace the `api(...)` call block (`~433-437`):

```tsx
      await api(
        event ? `/events/${event.id}` : "/submissions",
        event ? "PATCH" : "POST",
        event ? eventPatch(event, body) : body,
      );
      onDone();
```

with:

```tsx
      const patch = event ? eventPatch(event, body) : body;
      await api(
        event ? `/events/${event.id}` : "/submissions",
        event ? "PATCH" : "POST",
        patch,
      );
      await onSaved?.(patch);
      onDone();
```

- [ ] **Step 3: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: clean (existing callers pass no `onSaved`).

- [ ] **Step 4: Commit**

```bash
git add web/src/main.tsx
git commit -m "feat: EventForm surfaces its computed patch via onSaved"
```

---

### Task 5: AI tab — nav button, list, and load

**Files:**
- Modify: `web/src/main.tsx` — imports, `EventItem` type, state, `loadAi`, effect, nav button, tab body. Add small CSS in `web/src/style.css`.
- Modify: `web/src/style.css`.

- [ ] **Step 1: Imports and type**

Add to the imports in `main.tsx` (with the other `./...` imports, ~line 8):

```tsx
import { propagationCandidates, sourceGroup } from "./ai-review.mjs";
```

Add `ai_reviewed_at` to the `EventItem` type (`~line 48`, next to `ai_extracted`):

```tsx
  ai_reviewed_at?: string | null;
```

- [ ] **Step 2: State, loader, and tab effect**

In `App()` add state after `adminQuery` (`~line 728`):

```tsx
  const [aiEvents, setAiEvents] = useState<EventItem[]>([]),
    [aiReviewId, setAiReviewId] = useState<string | null>(null);
```

Add after the `refresh()` function (after `~line 799`):

```tsx
  async function loadAi() {
    const data = (await api("/review/ai")) as { events: EventItem[] };
    setAiEvents(data.events);
    return data.events;
  }
```

Add a tab effect after the existing `refresh()` effect (after `~line 805`):

```tsx
  useEffect(() => {
    if (EDITOR && !STATIC && tab === "ai") {
      loadAi();
    }
  }, [tab]);
```

- [ ] **Step 3: Derived groups / queue / current event**

Add after the `listEvents` memo (`~line 885`):

```tsx
  const aiGroups = useMemo(() => {
    const groups = new Map<string, { label: string; events: EventItem[] }>();
    for (const e of aiEvents) {
      const { key, label } = sourceGroup(e);
      if (!groups.has(key)) groups.set(key, { label, events: [] });
      groups.get(key)!.events.push(e);
    }
    for (const group of groups.values()) {
      group.events.sort((a, b) => {
        const ra = a.ai_reviewed_at ? 1 : 0;
        const rb = b.ai_reviewed_at ? 1 : 0;
        if (ra !== rb) return ra - rb;
        return a.start < b.start ? -1 : a.start > b.start ? 1 : 0;
      });
    }
    return [...groups.values()];
  }, [aiEvents]);
  const aiQueue = useMemo(() => {
    const list = [...aiEvents];
    list.sort((a, b) => {
      const ra = a.ai_reviewed_at ? 1 : 0;
      const rb = b.ai_reviewed_at ? 1 : 0;
      if (ra !== rb) return ra - rb;
      return a.start < b.start ? -1 : a.start > b.start ? 1 : 0;
    });
    return list;
  }, [aiEvents]);
  const aiCurrent = aiQueue.find((e) => e.id === aiReviewId) ?? null;
  const aiIndex = aiCurrent ? aiQueue.indexOf(aiCurrent) : -1;
  const aiReviewCount = (group: { events: EventItem[] }) =>
    tr("ai.countReview")
      .replace("{done}", String(group.events.filter((e) => e.ai_reviewed_at).length))
      .replace("{total}", String(group.events.length));
```

- [ ] **Step 4: Nav button**

After the Admin nav button (`~line 1010`), insert:

```tsx
          {!STATIC && EDITOR && (
            <button
              className={tab === "ai" ? "active" : ""}
              onClick={() => setTab("ai")}
            >
              {tr("ai.nav")}
            </button>
          )}
```

- [ ] **Step 5: Tab body**

Insert a new branch in the tab render chain, after the `admin` branch (`~line 1734`, before the final `: ( null )`):

```tsx
        ) : !STATIC && EDITOR && tab === "ai" ? (
          <section className="workspace">
            <p className="eyebrow">{tr("ai.eyebrow")}</p>
            <h1>{tr("ai.title")}</h1>
            <p className="intro">{tr("ai.intro")}</p>
            {aiEvents.length === 0 ? (
              <div className="empty">
                <div className="empty-symbol">✓</div>
                <h3>{tr("ai.empty")}</h3>
                <p>{tr("ai.emptyCopy")}</p>
              </div>
            ) : (
              aiGroups.map((group) => (
                <section key={group.key} className="ai-group">
                  <h2>{group.label}</h2>
                  <p className="muted">{aiReviewCount(group)}</p>
                  {group.events.map((e) => (
                    <article className="review-card" key={e.id}>
                      <div>
                        <span
                          className={
                            e.ai_reviewed_at
                              ? "source-state implemented"
                              : "source-state"
                          }
                        >
                          {e.ai_reviewed_at
                            ? tr("ai.reviewed")
                            : tr("ai.needsReview")}
                        </span>
                        <h3>{e.title}</h3>
                        <p>
                          {formatDate(e.start)} ·{" "}
                          {e.venue || tr("event.locationOpen")}
                        </p>
                      </div>
                      <button
                        className="primary"
                        onClick={() => setAiReviewId(e.id)}
                      >
                        {tr("review.inspect")}
                      </button>
                    </article>
                  ))}
                </section>
              ))
            )}
          </section>
```

- [ ] **Step 6: Minimal CSS**

Append to `web/src/style.css` (after the `.form-actions button` rule, `~line 1083`):

```css
.ai-group {
  padding: 18px 0;
  border-top: 1px solid var(--line);
}
.ai-group:first-of-type {
  border-top: 0;
}
.ai-group h2 {
  font-size: 19px;
  margin: 0 0 4px;
}
.ai-queue {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.ai-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 16px;
}
```

- [ ] **Step 7: Type-check and build**

Run: `cd web && npx tsc --noEmit && VITE_STATIC=1 npx vite build`
Expected: clean; the build includes the `darmstadt/` entry as before. The AI tab is invisible in the static build (guards).

- [ ] **Step 8: Commit**

```bash
git add web/src/main.tsx web/src/style.css
git commit -m "feat: AI review tab listing published AI events by source"
```

---

### Task 6: Queue modal — review actions and batch-fix propagation

**Files:**
- Modify: `web/src/main.tsx` — action handlers + AI modal.

- [ ] **Step 1: Action handlers**

Add after `aiReviewCount` (Task 5, Step 3):

```tsx
  async function advanceAi() {
    const fresh = await loadAi();
    const next = fresh.find((e) => !e.ai_reviewed_at);
    setAiReviewId(next?.id ?? null);
  }
  async function propagateFix(event: EventItem, patch: Record<string, unknown>) {
    const fresh = await loadAi();
    const group = fresh.filter((e) => sourceGroup(e).key === sourceGroup(event).key);
    const suggestions = propagationCandidates({ events: group, original: event, patch });
    for (const s of suggestions) {
      const label = tr(`form.${s.field}`);
      const lines = s.matches.map((m) => `− ${m.title}`).join("\n");
      const copy = tr("ai.propagationCopy")
        .replace("{field}", label)
        .replace("{old}", String(s.oldValue))
        .replace("{new}", String(s.newValue))
        .replace("{n}", String(s.matches.length));
      if (!window.confirm(`${tr("ai.propagationTitle")}\n\n${copy}\n\n${lines}`)) return;
      for (const m of s.matches) {
        await api(`/events/${m.id}`, "PATCH", { [s.field]: s.newValue });
      }
    }
  }
  async function markAiReviewed() {
    if (!aiCurrent) return;
    await api(`/events/${aiCurrent.id}`, "PATCH", {
      ai_reviewed_at: new Date().toISOString(),
    });
    setNotice(tr("toast.saved"));
    await advanceAi();
  }
  async function hideAiEvent() {
    if (!aiCurrent) return;
    if (!window.confirm(tr("ai.hideConfirm"))) return;
    await api(`/events/${aiCurrent.id}`, "PATCH", {
      status: "rejected",
      review_reason: "AI review: hidden",
      ai_reviewed_at: new Date().toISOString(),
    });
    setNotice(tr("ai.hidden"));
    await advanceAi();
  }
```

- [ ] **Step 2: The AI review modal**

Insert the modal alongside the existing `editing` modal (`~line 1946`):

```tsx
      {!STATIC && EDITOR && aiCurrent && (
        <Modal
          title={tr("ai.title")}
          closeLabel={tr("modal.close")}
          onClose={() => setAiReviewId(null)}
        >
          <div className="ai-queue">
            <button
              className="icon-button"
              disabled={aiIndex <= 0}
              onClick={() => setAiReviewId(aiQueue[aiIndex - 1].id)}
            >
              {tr("ai.prev")}
            </button>
            <span className="muted">
              {aiIndex + 1} / {aiQueue.length}
            </span>
            <button
              className="icon-button"
              disabled={aiIndex >= aiQueue.length - 1}
              onClick={() => setAiReviewId(aiQueue[aiIndex + 1].id)}
            >
              {tr("ai.next")}
            </button>
            <button
              className="icon-button"
              onClick={() => {
                const next = aiQueue.find(
                  (e, i) => i > aiIndex && !e.ai_reviewed_at,
                );
                setAiReviewId(
                  next?.id ??
                    aiQueue.find((e, i) => i < aiIndex && !e.ai_reviewed_at)?.id ??
                    aiReviewId,
                );
              }}
            >
              {tr("ai.skip")}
            </button>
          </div>
          <p className="muted">
            {sourceGroup(aiCurrent).label} · {tr("ai.auditLine")}
          </p>
          <EventForm
            event={aiCurrent}
            language={language}
            onSaved={async (patch) => {
              await api(`/events/${aiCurrent.id}`, "PATCH", {
                ai_reviewed_at: new Date().toISOString(),
              });
              await propagateFix(aiCurrent, patch);
            }}
            onDone={advanceAi}
          />
          <div className="ai-actions">
            <button className="primary" onClick={markAiReviewed}>
              {tr("ai.markReviewed")}
            </button>
            <button className="danger" onClick={hideAiEvent}>
              {tr("ai.hide")}
            </button>
          </div>
        </Modal>
      )}
```

- [ ] **Step 3: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: clean (EventForm now accepts `onSaved`).

- [ ] **Step 4: Run the full frontend test suite**

Run: `cd web && npm test`
Expected: PASS (39 existing + the 6 `ai-review` tests + i18n additions).

- [ ] **Step 5: Commit**

```bash
git add web/src/main.tsx
git commit -m "feat: AI review queue with mark-reviewed, hide, and batch-fix propagation"
```

---

### Task 7: Full verification

**Files:** none (verification only).

- [ ] **Step 1: Backend suite**

Run: `.venv/bin/python -m pytest tests -q`
Expected: PASS — 99 existing + the 3 new `ai_` tests = 102.

- [ ] **Step 2: Frontend suite + types + build**

Run: `cd web && npm test && npx tsc --noEmit && VITE_STATIC=1 npx vite build`
Expected: all tests pass, tsc clean, build succeeds with `dist/index.html`, `dist/darmstadt/index.html`, `dist/darmstadt/data.json`.

- [ ] **Step 3: Confirm the tool is local-only in the built app**

Run:
```bash
rg -l "ai\.nav|aiReviewId|propagationCandidates|/review/ai" web/dist/darmstadt/assets/*.js | wc -l
```
Expected: the count may be `0` (esbuild folds the `!STATIC` dead branch away) — but **a non-zero count is acceptable** because the render is dead at runtime: the AI tab renders only under `EDITOR && !STATIC`, and the static build sets `STATIC = true`. The authoritative gates are (a) this build ships `VITE_STATIC=1`, (b) the AI endpoint only exists on the local FastAPI backend (it is not deployed — Pages serves only `web/dist` + `data.json`), and (c) the manual smoke check in Step 5 shows no AI tab on the public preview. If the grep count is non-zero, note it here as expected dead code, not a leak.

- [ ] **Step 4: Rebuild static export and restart the dev server**

Run: `.venv/bin/python -m app.export_static`
Then confirm the dev server (`127.0.0.1:8765`, PID 54820) still serves the fresh `web/dist`. Do **not** kill it.

- [ ] **Step 5: Manual smoke check (editor only)**

Open the editor preview (`npx vite` with `VITE_EDITOR=1` against the local API) and verify:
- The **AI** nav tab appears; clicking it groups published AI events by source, unreviewed first with counts.
- Opening a row shows the queue modal; **prev/next/skip** move through the queue.
- Editing a `venue` that another same-source AI event shares shows the batch-fix confirm and, on confirm, fixes both.
- **Mark reviewed** moves on and shows the chip; **Hide from public** removes the event from the list and from the public preview.
- The public static preview (`127.0.0.1:8765/darmstadt/`) shows **no** AI tab.

- [ ] **Step 6: Record outcomes**

Delta: `tests/test_api.py` +3, `web/src/ai-review.mjs` +1 test file (6 tests), i18n +22 keys (en+de). Note any deviations in the plan file.

---

## Self-review (done at write time)

- **Spec coverage:** endpoint + marker (Task 1), propagation module (Task 2), grouping/list/load (Task 5), queue + actions + propagation UI (Task 6), i18n (Task 3), `onSaved` hook (Task 4), verification incl. local-only grep (Task 7). All decisions from the Q&A are represented: cleanup pass (no pipeline change), confirm-after-save propagation, same-source matching, propagation fields `{venue, address, title, start, end}`, mark-reviewed status, hide action.
- **Placeholders:** none — every step carries full code.
- **Type consistency:** `ai_reviewed_at` used identically across `EventItem`, the endpoint response, and the PATCH bodies; `sourceGroup` returns `{key, label}` everywhere; `propagationCandidates` returns `{field, oldValue, newValue, matches}` and is consumed the same way in tests and the modal.
- **Deviation from spec:** the i18n key list on the spec page included `ai.propagationConfirm`/`ai.propagationNone`; the plan omits them because the confirm uses the browser `window.confirm` dialog, so no custom button labels are needed.