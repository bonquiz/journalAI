# Phase 4 Polish & Portabilität — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build JSON-ZIP-Export + Import (mit Dry-Run und drei Konflikt-Modi), ergänze `/entries` um eine „Mehr laden"-Pagination, und validiere zwei aufgeschobene Polish-Items live.

**Architecture:** Zwei neue FastAPI-Router (`/api/export`, `/api/import`) mit zugehörigen Service-Modulen. `/api/entries` bleibt unverändert — es liefert bereits `{ total, items }`. Frontend bekommt einen neuen Settings-Abschnitt „Datenportabilität" und einen „Mehr laden"-Button in `/entries`. Alle DB-Operationen beim Import laufen in einer SQLAlchemy-Transaktion; Dry-Run rollt am Ende zurück.

**Tech Stack:** FastAPI + SQLAlchemy 2 + SQLCipher + Pydantic v2 • SvelteKit 2 + Svelte 5 runes + Vitest • pytest + TestClient (bestehendes Pattern).

---

## Spec

Dieses Plan implementiert `docs/superpowers/specs/2026-04-17-phase4-polish-design.md`. Bei Unklarheit die Spec konsultieren.

## Implementierungsreihenfolge

1. Pagination (frontend-only — Backend liefert `total` bereits)
2. Export (Service → Route → Frontend)
3. Import (Parser → Planner → Apply → Route → Frontend)
4. Polish-Items (Playwright-Runbook + MP3-Concat-Validierung)
5. Roadmap-Update

## Datei-Struktur

**Backend (neu):**
- `backend/app/services/export.py` — Builder für `entries.json`-Dict und ZIP-Stream.
- `backend/app/routes/export.py` — `GET /api/export`.
- `backend/app/services/import_.py` — Parser, Planner, Apply-Logik.
- `backend/app/routes/import_.py` — `POST /api/import` (multipart, dry_run + mode).
- `backend/tests/test_export.py` — Tests für Service + Route.
- `backend/tests/test_import.py` — Tests für Service + Route.

**Backend (modifiziert):**
- `backend/app/main.py` — zwei neue Router registrieren.
- `backend/app/services/tts.py` — Docstring präzisieren (Polish-Item).

**Frontend (neu):**
- `frontend/src/lib/portability.ts` — API-Client für Export/Import.
- `frontend/src/lib/components/DataPortability.svelte` — Settings-Abschnitt.
- `frontend/tests/portability.test.ts` — Unit-Tests für den Client.
- `frontend/tests/entries-pagination.test.ts` — Unit-Test für Load-More-Logik.

**Frontend (modifiziert):**
- `frontend/src/routes/entries/+page.svelte` — Pagination-State + „Mehr laden"-Button.
- `frontend/src/routes/settings/+page.svelte` — DataPortability-Komponente einbinden.

**Docs (modifiziert):**
- `README.md` — neuer Abschnitt „E2E-Tests live ausführen".
- `backend/app/services/tts.py` — Docstring (oben erwähnt).
- Memory-Datei: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md` — nach jedem Teil-Commit updaten.

---

# Teil 1: Pagination `/entries`

Backend-API liefert schon `{ total: int, items: Entry[] }`. Keine Server-Änderung nötig.

### Task 1: Frontend-Unit-Test für Load-More-Logik

**Files:**
- Create: `frontend/tests/entries-pagination.test.ts`

- [ ] **Step 1: Write the failing test**

Prüft reine Logik-Funktion für das State-Management. Wir extrahieren die Logik in eine pure Helper-Funktion, damit sie isoliert testbar ist.

```typescript
// frontend/tests/entries-pagination.test.ts
import { describe, it, expect } from "vitest";
import { mergePage, hasMore } from "../src/lib/entries-pagination";

type Item = { id: string };

describe("entries pagination", () => {
  it("mergePage appends new items at the end", () => {
    const prev: Item[] = [{ id: "a" }, { id: "b" }];
    const next: Item[] = [{ id: "c" }];
    expect(mergePage(prev, next)).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }]);
  });

  it("mergePage deduplicates by id (last write wins on duplicates)", () => {
    const prev: Item[] = [{ id: "a" }];
    const next: Item[] = [{ id: "a" }, { id: "b" }];
    expect(mergePage(prev, next)).toEqual([{ id: "a" }, { id: "b" }]);
  });

  it("hasMore is true when loaded < total", () => {
    expect(hasMore(50, 137)).toBe(true);
  });

  it("hasMore is false when loaded >= total", () => {
    expect(hasMore(137, 137)).toBe(false);
    expect(hasMore(200, 137)).toBe(false);
  });

  it("hasMore is false when total is 0", () => {
    expect(hasMore(0, 0)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/entries-pagination.test.ts`
Expected: FAIL mit „Cannot find module '../src/lib/entries-pagination'".

- [ ] **Step 3: Create the helper module**

```typescript
// frontend/src/lib/entries-pagination.ts
export function mergePage<T extends { id: string }>(prev: T[], next: T[]): T[] {
  const seen = new Set(prev.map((x) => x.id));
  const extras = next.filter((x) => !seen.has(x.id));
  return [...prev, ...extras];
}

export function hasMore(loaded: number, total: number): boolean {
  return loaded < total;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/entries-pagination.test.ts`
Expected: PASS (5 Tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/entries-pagination.ts frontend/tests/entries-pagination.test.ts
git commit -m "feat(entries): load-more helpers (mergePage, hasMore)"
```

### Task 2: Pagination-State in `/entries/+page.svelte`

**Files:**
- Modify: `frontend/src/routes/entries/+page.svelte`

- [ ] **Step 1: Ersetze `load()` durch pagination-fähige Variante**

Ändere den Import-Block am Anfang des `<script>`:

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { Recorder, transcribe } from "$lib/audio";
  import EntryCard from "$lib/components/EntryCard.svelte";
  import SearchResultCard from "$lib/components/SearchResultCard.svelte";
  import SearchToggle from "$lib/components/SearchToggle.svelte";
  import { searchStore } from "$lib/stores/search.svelte";
  import { mergePage, hasMore } from "$lib/entries-pagination";

  type Item = { id: string; title: string; entry_date: string; content: string; tags: string[] };

  const PAGE_SIZE = 50;

  let allTags = $state<string[]>([]);
  let activeTags = $state<Set<string>>(new Set());
  let q = $state("");
  let items = $state<Item[]>([]);
  let total = $state(0);
  let loading = $state(false);

  let recording = $state(false);
  let transcribing = $state(false);
  let recorder: Recorder | null = null;
  let micError: string | null = $state(null);
```

Ersetze die Funktion `load()` durch `loadFirstPage()` und füge `loadMore()` hinzu:

```svelte
  async function fetchPage(offset: number): Promise<{ items: Item[]; total: number }> {
    const tags = Array.from(activeTags).join(",");
    return await api<{ items: Item[]; total: number }>(
      `/api/entries?tags=${encodeURIComponent(tags)}&q=${encodeURIComponent(q)}`
      + `&offset=${offset}&limit=${PAGE_SIZE}`,
    );
  }

  async function loadFirstPage() {
    loading = true;
    try {
      const data = await fetchPage(0);
      items = data.items;
      total = data.total;
    } finally {
      loading = false;
    }
  }

  async function loadMore() {
    if (loading) return;
    loading = true;
    try {
      const data = await fetchPage(items.length);
      items = mergePage(items, data.items);
      total = data.total;
    } finally {
      loading = false;
    }
  }
```

Update `toggle()` und `onKeywordSubmit()` um `loadFirstPage()` zu rufen statt `load()`:

```svelte
  function toggle(t: string) {
    if (activeTags.has(t)) activeTags.delete(t);
    else activeTags.add(t);
    activeTags = new Set(activeTags);
    loadFirstPage();
  }

  function onKeywordSubmit(e: SubmitEvent) {
    e.preventDefault();
    loadFirstPage();
  }
```

Update `onMount()`:

```svelte
  onMount(async () => {
    allTags = await api<string[]>("/api/tags");
    await loadFirstPage();
  });
```

- [ ] **Step 2: „Mehr laden"-Button im Template**

Ersetze den keyword-mode-Block (`{:else}` im äußeren `{#if searchStore.mode === "semantic"}`):

```svelte
{:else}
  {#if loading && items.length === 0}<p>Lade…</p>{/if}
  <div class="list">
    {#each items as e (e.id)}
      <EntryCard {e} />
    {/each}
    {#if !loading && items.length === 0}
      <p class="muted">Keine Einträge.</p>
    {/if}
  </div>
  {#if hasMore(items.length, total)}
    <div class="load-more">
      <button type="button" onclick={loadMore} disabled={loading}>
        {loading ? "Lade…" : `Mehr laden (${items.length}/${total})`}
      </button>
    </div>
  {/if}
{/if}
```

Füge CSS am Ende des `<style>`-Blocks hinzu:

```svelte
  .load-more { display: flex; justify-content: center; margin: 1rem 0 2rem; }
  .load-more button { min-height: 44px; padding: 0.6rem 1.25rem; }
```

- [ ] **Step 3: Manueller Smoke-Test**

Run: `cd frontend && npm run check`
Expected: PASS (keine Typ-Fehler).

Start Dev-Server (`cd frontend && npm run dev` + Backend über `deploy/docker-compose.yml`) und erstelle ≥51 Test-Einträge. Verifiziere:
- Initial sind 50 geladen, Button zeigt „Mehr laden (50/51)".
- Klick auf Button → 51 Einträge sichtbar, Button verschwindet.
- Tag-Filter und Suche resetten die Liste.
- Im semantischen Such-Modus ist der Load-More-Button nicht sichtbar.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/entries/+page.svelte
git commit -m "feat(entries): load-more pagination (page size 50)"
```

### Task 3: Roadmap-Update nach Teil 1

**Files:**
- Modify: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`

- [ ] **Step 1: Abschnitt „In Arbeit" auf Phase 4 setzen, Pagination unter „Erledigt" verschieben**

Füge unter `## ✅ Erledigt` einen neuen Abschnitt ein, direkt nach „Phase 2 Semantische Suche":

```markdown
### Phase 4 Polish & Portabilität (`v0.4.0-polish`, in Arbeit)
- **Pagination /entries:** Load-More-Button (Page-Size 50), `mergePage`/`hasMore`-Helper, Filter/Suche resetten die Liste, semantische Suche umgeht Pagination.
```

Passe in `## 📋 Offen` den Eintrag „Pagination `/entries`" so an, dass er entfernt ist. Setze `## 🔧 In Arbeit` auf:

```markdown
## 🔧 In Arbeit
Phase 4 — Export/Import + Polish-Items stehen noch aus.
```

Aktualisiere das Datum im Header-Kommentar („Letzte Aktualisierung dieser Datei: 2026-04-17").

- [ ] **Step 2: Kein Commit — Memory-Datei ist außerhalb des Repos**

Die Roadmap liegt unter `~/.claude/projects/...` und wird nicht versioniert.

---

# Teil 2: Export

### Task 4: `build_export_payload` — Dict-Builder

**Files:**
- Create: `backend/app/services/export.py`
- Create: `backend/tests/test_export.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_export.py
import json

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag
from app.schemas.entries import new_id
from app.services.export import build_export_payload


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.query(AppSettings).delete()
        db.commit()


def _clear():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.commit()


def test_build_export_payload_empty():
    _clear()
    with SessionLocal() as db:
        payload = build_export_payload(db)
    assert payload["version"] == "1"
    assert payload["app"] == "journalAI"
    assert "exported_at" in payload
    assert payload["entries"] == []
    assert payload["tags"] == []


def test_build_export_payload_with_entry():
    _clear()
    with SessionLocal() as db:
        db.add(Tag(name="work"))
        db.add(Tag(name="reflection"))
        eid = new_id()
        e = Entry(
            id=eid,
            entry_date=__import__("datetime").date(2026, 4, 17),
            title="Hello",
            content="# heading\nbody",
            raw_transcript="raw",
            chat_history=json.dumps([{"role": "user", "content": "hi"}]),
        )
        db.add(e)
        db.add(EntryTag(entry_id=eid, tag_name="work"))
        db.add(EntryTag(entry_id=eid, tag_name="reflection"))
        db.commit()
        payload = build_export_payload(db)

    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["id"] == eid
    assert entry["entry_date"] == "2026-04-17"
    assert entry["title"] == "Hello"
    assert entry["content"] == "# heading\nbody"
    assert entry["raw_transcript"] == "raw"
    assert entry["chat_history"] == [{"role": "user", "content": "hi"}]
    assert sorted(entry["tags"]) == ["reflection", "work"]
    assert "created_at" in entry and "updated_at" in entry

    tag_names = sorted(t["name"] for t in payload["tags"])
    assert tag_names == ["reflection", "work"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_export.py -v`
Expected: FAIL mit „No module named 'app.services.export'".

- [ ] **Step 3: Implement `build_export_payload`**

```python
# backend/app/services/export.py
"""Export-Service: baut ein Dict im Export-Format (v1)."""
import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.tag import Tag
from app.utc import utc_now

EXPORT_VERSION = "1"


def build_export_payload(db: Session) -> dict[str, Any]:
    """Baut das Export-Dict. Reiner Builder, ohne I/O."""
    entries_out: list[dict[str, Any]] = []
    for e in db.query(Entry).order_by(Entry.entry_date.desc(), Entry.created_at.desc()).all():
        entries_out.append({
            "id": e.id,
            "entry_date": e.entry_date.isoformat(),
            "title": e.title,
            "content": e.content,
            "tags": sorted({link.tag_name for link in e.tags}),
            "raw_transcript": e.raw_transcript,
            "chat_history": json.loads(e.chat_history) if e.chat_history else None,
            "created_at": e.created_at.isoformat() + ("Z" if e.created_at.tzinfo is None else ""),
            "updated_at": e.updated_at.isoformat() + ("Z" if e.updated_at.tzinfo is None else ""),
        })

    tags_out = [{"name": t.name} for t in db.query(Tag).order_by(Tag.name).all()]

    return {
        "version": EXPORT_VERSION,
        "exported_at": utc_now().isoformat() + "Z",
        "app": "journalAI",
        "entries": entries_out,
        "tags": tags_out,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_export.py -v`
Expected: PASS (2 Tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export.py backend/tests/test_export.py
git commit -m "feat(export): build_export_payload builder"
```

### Task 5: `stream_export_zip` — ZIP-Generator

**Files:**
- Modify: `backend/app/services/export.py`
- Modify: `backend/tests/test_export.py`

- [ ] **Step 1: Write the failing test**

Hänge am Ende von `test_export.py` an:

```python
import io
import zipfile
from app.services.export import stream_export_zip


def test_stream_export_zip_structure():
    _clear()
    with SessionLocal() as db:
        db.add(Tag(name="work"))
        db.add(Entry(
            id=new_id(),
            entry_date=__import__("datetime").date(2026, 4, 17),
            title="T", content="C",
        ))
        db.commit()
        chunks = list(stream_export_zip(db))

    buf = io.BytesIO(b"".join(chunks))
    with zipfile.ZipFile(buf, "r") as zf:
        names = zf.namelist()
        assert names == ["entries.json"]
        data = json.loads(zf.read("entries.json").decode("utf-8"))
        assert data["version"] == "1"
        assert len(data["entries"]) == 1
        assert data["entries"][0]["title"] == "T"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_export.py::test_stream_export_zip_structure -v`
Expected: FAIL mit „cannot import name 'stream_export_zip'".

- [ ] **Step 3: Implement `stream_export_zip`**

Hänge am Ende von `backend/app/services/export.py` an:

```python
import io
import zipfile
from collections.abc import Iterator


def stream_export_zip(db: Session) -> Iterator[bytes]:
    """Erzeugt ein In-Memory-ZIP mit `entries.json` und gibt es als Byte-Chunks zurück."""
    payload = build_export_payload(db)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("entries.json", json.dumps(payload, ensure_ascii=False, indent=2))
    buf.seek(0)
    chunk_size = 64 * 1024
    while True:
        chunk = buf.read(chunk_size)
        if not chunk:
            break
        yield chunk
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/pytest tests/test_export.py -v`
Expected: PASS (3 Tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export.py backend/tests/test_export.py
git commit -m "feat(export): stream_export_zip generator"
```

### Task 6: Route `GET /api/export`

**Files:**
- Create: `backend/app/routes/export.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_export.py`

- [ ] **Step 1: Write the failing route-level test**

Hänge am Ende von `test_export.py` an:

```python
from fastapi.testclient import TestClient
from app.auth.sessions import create_session
from app.main import app


def test_get_export_requires_auth():
    with TestClient(app) as c:
        r = c.get("/api/export")
    assert r.status_code in (401, 403)


def test_get_export_returns_zip():
    _clear()
    with SessionLocal() as db:
        db.add(Entry(
            id=new_id(),
            entry_date=__import__("datetime").date(2026, 4, 17),
            title="Export-Test", content="Content",
        ))
        db.commit()
    sid = create_session()
    with TestClient(app) as c:
        r = c.get("/api/export", cookies={"session": sid, "csrf": "t"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    assert "journalai-export-" in r.headers["content-disposition"]

    buf = io.BytesIO(r.content)
    with zipfile.ZipFile(buf, "r") as zf:
        data = json.loads(zf.read("entries.json").decode("utf-8"))
    assert data["version"] == "1"
    assert any(e["title"] == "Export-Test" for e in data["entries"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_export.py::test_get_export_returns_zip -v`
Expected: FAIL mit 404 oder ähnlich (Route existiert noch nicht).

- [ ] **Step 3: Implement route**

```python
# backend/app/routes/export.py
"""Export-Route: GET /api/export → ZIP-Download."""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.db import SessionLocal
from app.services.export import stream_export_zip
from app.utc import utc_now

router = APIRouter(prefix="/api/export")


@router.get("")
async def export_zip() -> StreamingResponse:
    db = SessionLocal()
    date_tag = utc_now().date().isoformat()
    filename = f"journalai-export-{date_tag}.zip"

    def _iter():
        try:
            yield from stream_export_zip(db)
        finally:
            db.close()

    return StreamingResponse(
        _iter(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, füge nach `from app.routes.entries import router as entries_router` ein:

```python
from app.routes.export import router as export_router
```

Und nach `app.include_router(entries_router)` ein:

```python
app.include_router(export_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_export.py -v`
Expected: PASS (5 Tests, inkl. Auth-Test).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/export.py backend/app/main.py backend/tests/test_export.py
git commit -m "feat(export): GET /api/export route streams zip"
```

### Task 7: Frontend — DataPortability-Komponente (Export-Button)

**Files:**
- Create: `frontend/src/lib/portability.ts`
- Create: `frontend/src/lib/components/DataPortability.svelte`
- Create: `frontend/tests/portability.test.ts`
- Modify: `frontend/src/routes/settings/+page.svelte`

- [ ] **Step 1: Write the failing test for the API client**

```typescript
// frontend/tests/portability.test.ts
import { describe, it, expect } from "vitest";
import { exportUrl } from "../src/lib/portability";

describe("portability client", () => {
  it("exportUrl returns relative path to export endpoint", () => {
    expect(exportUrl()).toBe("/api/export");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run tests/portability.test.ts`
Expected: FAIL mit „Cannot find module '../src/lib/portability'".

- [ ] **Step 3: Implement client**

```typescript
// frontend/src/lib/portability.ts
/** Portabilitäts-API: Export (Download via Anchor-Tag) + Import (multipart POST). */

export function exportUrl(): string {
  return "/api/export";
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run tests/portability.test.ts`
Expected: PASS (1 Test).

- [ ] **Step 5: Implement DataPortability-Komponente**

```svelte
<!-- frontend/src/lib/components/DataPortability.svelte -->
<script lang="ts">
  import { exportUrl } from "$lib/portability";
</script>

<section class="card">
  <h2>Datenportabilität</h2>

  <div class="block">
    <h3>Export</h3>
    <p class="muted">
      Lade alle Einträge und Tags als ZIP mit <code>entries.json</code> (Format v1) herunter.
    </p>
    <a class="btn" href={exportUrl()} download>Export herunterladen (.zip)</a>
  </div>
</section>

<style>
  .card {
    margin: 1rem 0;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .block { margin-bottom: 1rem; }
  .block:last-child { margin-bottom: 0; }
  h3 { margin: 0 0 0.35rem; font-size: 1rem; }
  .muted { color: var(--muted); font-size: 0.9em; margin: 0 0 0.6rem; }
  .btn {
    display: inline-block;
    padding: 0.6rem 1rem;
    min-height: 44px;
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius);
    text-decoration: none;
  }
</style>
```

- [ ] **Step 6: Wire into /settings**

Öffne `frontend/src/routes/settings/+page.svelte`. Füge oben im Import-Block hinzu:

```svelte
  import DataPortability from "$lib/components/DataPortability.svelte";
```

Und direkt vor der schließenden `{:else}`-Branch (also nach dem 2FA-Card, vor `{/if}`) einfügen:

```svelte
  <DataPortability />
```

- [ ] **Step 7: Verify and commit**

Run: `cd frontend && npm run check && npx vitest run tests/portability.test.ts`
Expected: keine Typ-Fehler, 1 Test PASS.

```bash
git add frontend/src/lib/portability.ts frontend/src/lib/components/DataPortability.svelte frontend/tests/portability.test.ts frontend/src/routes/settings/+page.svelte
git commit -m "feat(export): settings button + portability client"
```

### Task 8: Roadmap-Update nach Teil 2

**Files:**
- Modify: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`

- [ ] **Step 1: Ergänze unter Phase 4 „Erledigt"**

Hänge an den Phase-4-Block an:

```markdown
- **Export:** services/export.py (build_export_payload + stream_export_zip), GET /api/export streamt ZIP mit entries.json (Format v1), Settings-Komponente DataPortability mit Download-Button.
```

Datum aktualisieren.

---

# Teil 3: Import

### Task 9: `parse_export_zip` — Parser und Schema-Validierung

**Files:**
- Create: `backend/app/services/import_.py`
- Create: `backend/tests/test_import.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_import.py
import io
import json
import zipfile

import pytest

from app.auth.password import hash_password
from app.db import Base, SessionLocal, engine
from app.models.entry import Entry
from app.models.settings import AppSettings
from app.models.tag import EntryTag, Tag
from app.services.import_ import ImportError as AppImportError, parse_export_zip


def setup_module():
    engine.dispose()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.merge(AppSettings(id=1, password_hash=hash_password("pw")))
        db.commit()


def teardown_module():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.query(AppSettings).delete()
        db.commit()


def _zip_with(payload: dict | str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        zf.writestr("entries.json", body)
    return buf.getvalue()


def _valid_payload() -> dict:
    return {
        "version": "1",
        "exported_at": "2026-04-17T10:00:00Z",
        "app": "journalAI",
        "entries": [{
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "entry_date": "2026-04-17",
            "title": "T",
            "content": "C",
            "tags": ["work"],
            "raw_transcript": None,
            "chat_history": None,
            "created_at": "2026-04-17T10:00:00Z",
            "updated_at": "2026-04-17T10:00:00Z",
        }],
        "tags": [{"name": "work"}],
    }


def test_parse_valid_zip():
    payload = parse_export_zip(_zip_with(_valid_payload()))
    assert payload["version"] == "1"
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["title"] == "T"


def test_parse_rejects_missing_entries_json():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("other.json", "{}")
    with pytest.raises(AppImportError, match="entries.json"):
        parse_export_zip(buf.getvalue())


def test_parse_rejects_wrong_version():
    p = _valid_payload()
    p["version"] = "2"
    with pytest.raises(AppImportError, match="version"):
        parse_export_zip(_zip_with(p))


def test_parse_rejects_invalid_json():
    with pytest.raises(AppImportError, match="JSON"):
        parse_export_zip(_zip_with("not-json"))


def test_parse_rejects_corrupt_zip():
    with pytest.raises(AppImportError, match="ZIP"):
        parse_export_zip(b"not-a-zip-file")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: FAIL mit „No module named 'app.services.import_'".

- [ ] **Step 3: Implement parser**

```python
# backend/app/services/import_.py
"""Import-Service: Parse, Plan, Apply für Export-ZIPs."""
import io
import json
import zipfile
from typing import Any

SUPPORTED_VERSIONS = {"1"}


class ImportError(Exception):
    """Geworfen bei Format-/Validierungs-Fehlern. Route-Layer mappt auf HTTP 400."""


def parse_export_zip(blob: bytes) -> dict[str, Any]:
    """Validiert und parst ein Export-ZIP. Wirft ImportError bei Fehlern."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob), "r")
    except zipfile.BadZipFile as exc:
        raise ImportError("ungültiges ZIP") from exc

    with zf:
        if "entries.json" not in zf.namelist():
            raise ImportError("entries.json fehlt im ZIP")
        try:
            raw = zf.read("entries.json").decode("utf-8")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ImportError(f"entries.json ist kein gültiges JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ImportError("entries.json muss ein Objekt sein")

    version = payload.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise ImportError(f"unbekannte version: {version!r}")

    if not isinstance(payload.get("entries"), list):
        raise ImportError("entries muss ein Array sein")
    if not isinstance(payload.get("tags", []), list):
        raise ImportError("tags muss ein Array sein")

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: PASS (5 Tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_.py backend/tests/test_import.py
git commit -m "feat(import): parse_export_zip validator"
```

### Task 10: `plan_import` — Dry-Run-Berechnung

**Files:**
- Modify: `backend/app/services/import_.py`
- Modify: `backend/tests/test_import.py`

- [ ] **Step 1: Write the failing tests**

Hänge am Ende von `test_import.py` an:

```python
from app.schemas.entries import new_id
from app.services.import_ import plan_import


def _clear():
    with SessionLocal() as db:
        db.query(EntryTag).delete()
        db.query(Entry).delete()
        db.query(Tag).delete()
        db.commit()


def test_plan_empty_db_all_new():
    _clear()
    payload = _valid_payload()
    with SessionLocal() as db:
        plan = plan_import(db, payload)
    assert plan["total_in_file"] == 1
    assert plan["new_entries"] == 1
    assert plan["conflicts"] == 0
    assert plan["tags_new"] == 1
    assert plan["tags_merged"] == 0


def test_plan_conflict_counts_existing_ids():
    _clear()
    existing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with SessionLocal() as db:
        db.add(Entry(
            id=existing_id,
            entry_date=__import__("datetime").date(2026, 4, 1),
            title="Existing", content="x",
        ))
        db.commit()
        plan = plan_import(db, _valid_payload())
    assert plan["new_entries"] == 0
    assert plan["conflicts"] == 1


def test_plan_tag_counts():
    _clear()
    with SessionLocal() as db:
        db.add(Tag(name="work"))  # schon da
        db.commit()
        plan = plan_import(db, _valid_payload())
    assert plan["tags_new"] == 0
    assert plan["tags_merged"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: FAIL (neue Tests, `plan_import` existiert nicht).

- [ ] **Step 3: Implement `plan_import`**

Hänge am Ende von `import_.py` an:

```python
from sqlalchemy.orm import Session

from app.models.entry import Entry
from app.models.tag import Tag


def plan_import(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    """Zählt Neu/Konflikte, ohne zu schreiben. Tag-Zählung ist modus-unabhängig."""
    entries = payload.get("entries", [])
    total = len(entries)
    incoming_ids = {e["id"] for e in entries if isinstance(e, dict) and "id" in e}

    existing_ids: set[str] = set()
    if incoming_ids:
        rows = db.query(Entry.id).filter(Entry.id.in_(incoming_ids)).all()
        existing_ids = {r[0] for r in rows}

    conflicts = len(existing_ids & incoming_ids)
    new_entries = total - conflicts

    incoming_tag_names: set[str] = set()
    for t in payload.get("tags", []):
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            incoming_tag_names.add(t["name"])
    # Tags können auch nur über entries.tags[] kommen
    for e in entries:
        if isinstance(e, dict):
            for name in e.get("tags", []) or []:
                if isinstance(name, str):
                    incoming_tag_names.add(name)

    existing_tag_names: set[str] = set()
    if incoming_tag_names:
        rows = db.query(Tag.name).filter(Tag.name.in_(incoming_tag_names)).all()
        existing_tag_names = {r[0] for r in rows}

    tags_merged = len(existing_tag_names & incoming_tag_names)
    tags_new = len(incoming_tag_names) - tags_merged

    return {
        "total_in_file": total,
        "new_entries": new_entries,
        "conflicts": conflicts,
        "tags_new": tags_new,
        "tags_merged": tags_merged,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: PASS (8 Tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_.py backend/tests/test_import.py
git commit -m "feat(import): plan_import dry-run calculator"
```

### Task 11: `apply_import` — Modus `skip`

**Files:**
- Modify: `backend/app/services/import_.py`
- Modify: `backend/tests/test_import.py`

- [ ] **Step 1: Write the failing test**

Hänge am Ende von `test_import.py` an:

```python
from app.services.import_ import apply_import


def test_apply_skip_new_entries_only():
    _clear()
    with SessionLocal() as db:
        result = apply_import(db, _valid_payload(), mode="skip")
        db.commit()
    assert result["would_apply"] == 1
    assert result["new_entries"] == 1
    assert result["conflicts"] == 0
    assert result["errors"] == []

    with SessionLocal() as db:
        e = db.get(Entry, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        assert e is not None
        assert e.title == "T"
        tag_names = {link.tag_name for link in e.tags}
        assert tag_names == {"work"}


def test_apply_skip_preserves_existing_on_conflict():
    _clear()
    existing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with SessionLocal() as db:
        db.add(Entry(
            id=existing_id,
            entry_date=__import__("datetime").date(2026, 4, 1),
            title="ORIGINAL", content="orig",
        ))
        db.commit()

        result = apply_import(db, _valid_payload(), mode="skip")
        db.commit()

    assert result["new_entries"] == 0
    assert result["conflicts"] == 1
    assert result["would_apply"] == 0

    with SessionLocal() as db:
        e = db.get(Entry, existing_id)
        assert e.title == "ORIGINAL"  # unverändert
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `apply_import` with skip-mode**

Hänge am Ende von `import_.py` an:

```python
from datetime import date as _date, datetime

from app.models.entry import Entry as EntryModel
from app.models.tag import EntryTag, Tag as TagModel
from app.schemas.entries import new_id as new_entry_id
from app.utc import utc_now

VALID_MODES = {"skip", "copy", "overwrite"}


def _parse_date(v: Any) -> _date:
    if isinstance(v, _date):
        return v
    return _date.fromisoformat(str(v))


def _ensure_tag(db: Session, name: str) -> None:
    if db.get(TagModel, name) is None:
        db.add(TagModel(name=name))


def _set_entry_tags(db: Session, entry_id: str, names: list[str]) -> None:
    db.query(EntryTag).filter(EntryTag.entry_id == entry_id).delete()
    for n in set(names):
        _ensure_tag(db, n)
        db.add(EntryTag(entry_id=entry_id, tag_name=n))


def apply_import(
    db: Session,
    payload: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    """Schreibt Import in die DB. Caller ist verantwortlich für Commit/Rollback."""
    if mode not in VALID_MODES:
        raise ImportError(f"invalid mode: {mode!r}")

    entries = payload.get("entries", [])
    existing_ids: set[str] = set()
    incoming_ids = {e["id"] for e in entries if isinstance(e, dict) and "id" in e}
    if incoming_ids:
        rows = db.query(EntryModel.id).filter(EntryModel.id.in_(incoming_ids)).all()
        existing_ids = {r[0] for r in rows}

    # Ensure all tags exist first
    tag_names_all: set[str] = set()
    for t in payload.get("tags", []):
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            tag_names_all.add(t["name"])
    for e in entries:
        if isinstance(e, dict):
            for n in e.get("tags", []) or []:
                if isinstance(n, str):
                    tag_names_all.add(n)
    for name in tag_names_all:
        _ensure_tag(db, name)

    new_count = 0
    conflict_count = 0
    errors: list[dict[str, Any]] = []

    for idx, raw in enumerate(entries):
        if not isinstance(raw, dict) or "id" not in raw:
            errors.append({"index": idx, "id": None, "reason": "missing id"})
            continue
        eid = raw["id"]
        is_conflict = eid in existing_ids

        try:
            entry_date = _parse_date(raw["entry_date"])
            title = str(raw["title"])
            content = str(raw["content"])
            tags = list(raw.get("tags") or [])
            raw_transcript = raw.get("raw_transcript")
            chat_history = raw.get("chat_history")
            chat_history_json = json.dumps(chat_history) if chat_history else None
        except (KeyError, ValueError) as exc:
            errors.append({"index": idx, "id": eid, "reason": str(exc)})
            continue

        if is_conflict:
            conflict_count += 1
            if mode == "skip":
                continue
            # copy/overwrite handled in later tasks — placeholder raises
            raise NotImplementedError(f"mode {mode} wird in einem späteren Task implementiert")
        else:
            new_count += 1
            db.add(EntryModel(
                id=eid,
                entry_date=entry_date,
                title=title,
                content=content,
                raw_transcript=raw_transcript,
                chat_history=chat_history_json,
            ))
            db.flush()  # damit EntryTag-FK auflösbar
            _set_entry_tags(db, eid, tags)

    would_apply = new_count if mode == "skip" else new_count + conflict_count

    return {
        "mode": mode,
        "total_in_file": len(entries),
        "new_entries": new_count,
        "conflicts": conflict_count,
        "would_apply": would_apply,
        "tags_new": 0,  # wird in Task 13 korrekt gefüllt
        "tags_merged": 0,
        "errors": errors,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: PASS (10 Tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_.py backend/tests/test_import.py
git commit -m "feat(import): apply_import skip-mode"
```

### Task 12: `apply_import` — Modus `copy`

**Files:**
- Modify: `backend/app/services/import_.py`
- Modify: `backend/tests/test_import.py`

- [ ] **Step 1: Write the failing test**

Hänge am Ende von `test_import.py` an:

```python
def test_apply_copy_creates_new_entry_on_conflict():
    from datetime import date
    _clear()
    existing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with SessionLocal() as db:
        db.add(Entry(
            id=existing_id,
            entry_date=date(2026, 4, 1),
            title="ORIGINAL", content="orig",
        ))
        db.commit()

        result = apply_import(db, _valid_payload(), mode="copy")
        db.commit()

        all_entries = db.query(Entry).all()

    assert result["conflicts"] == 1
    assert result["new_entries"] == 0
    assert result["would_apply"] == 1

    assert len(all_entries) == 2
    original = next(e for e in all_entries if e.id == existing_id)
    copy = next(e for e in all_entries if e.id != existing_id)
    assert original.title == "ORIGINAL"
    assert copy.title == "T"  # aus _valid_payload
    assert copy.entry_date.isoformat() == "2026-04-17"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_import.py::test_apply_copy_creates_new_entry_on_conflict -v`
Expected: FAIL mit `NotImplementedError`.

- [ ] **Step 3: Implement copy-mode**

In `import_.py`, ersetze den Block

```python
        if is_conflict:
            conflict_count += 1
            if mode == "skip":
                continue
            # copy/overwrite handled in later tasks — placeholder raises
            raise NotImplementedError(f"mode {mode} wird in einem späteren Task implementiert")
```

durch

```python
        if is_conflict:
            conflict_count += 1
            if mode == "skip":
                continue
            if mode == "copy":
                new_id_val = new_entry_id()
                db.add(EntryModel(
                    id=new_id_val,
                    entry_date=entry_date,
                    title=title,
                    content=content,
                    raw_transcript=raw_transcript,
                    chat_history=chat_history_json,
                ))
                db.flush()
                _set_entry_tags(db, new_id_val, tags)
                continue
            # overwrite handled in Task 13
            raise NotImplementedError(f"mode {mode} wird in einem späteren Task implementiert")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: PASS (11 Tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_.py backend/tests/test_import.py
git commit -m "feat(import): apply_import copy-mode"
```

### Task 13: `apply_import` — Modus `overwrite` + Tag-Zählung + Error-Collection

**Files:**
- Modify: `backend/app/services/import_.py`
- Modify: `backend/tests/test_import.py`

- [ ] **Step 1: Write the failing tests**

Hänge am Ende von `test_import.py` an:

```python
def test_apply_overwrite_replaces_existing_and_invalidates_embedding():
    from datetime import date, datetime
    _clear()
    existing_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    with SessionLocal() as db:
        db.add(Entry(
            id=existing_id,
            entry_date=date(2026, 4, 1),
            title="ORIGINAL", content="orig",
            embedding=b"\x00\x01\x02",
            embedding_model="old-model",
            embedding_updated_at=datetime(2026, 1, 1),
        ))
        db.commit()

        result = apply_import(db, _valid_payload(), mode="overwrite")
        db.commit()

    assert result["conflicts"] == 1
    assert result["would_apply"] == 1

    with SessionLocal() as db:
        e = db.get(Entry, existing_id)
        assert e.title == "T"
        assert e.content == "C"
        assert e.embedding is None
        assert e.embedding_model is None
        assert e.embedding_updated_at is None


def test_apply_collects_errors_but_continues():
    _clear()
    payload = _valid_payload()
    payload["entries"].insert(0, {
        "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "entry_date": "INVALID-DATE",
        "title": "Bad", "content": "x",
        "tags": [],
    })
    with SessionLocal() as db:
        result = apply_import(db, payload, mode="skip")
        db.commit()
    assert len(result["errors"]) == 1
    assert result["errors"][0]["id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert result["new_entries"] == 1  # der valide wurde geschrieben


def test_apply_reports_tag_counts():
    _clear()
    with SessionLocal() as db:
        db.add(Tag(name="work"))  # existiert bereits
        db.commit()
        result = apply_import(db, _valid_payload(), mode="skip")
        db.commit()
    assert result["tags_merged"] == 1
    assert result["tags_new"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: FAIL (overwrite-Test, Tag-Counts-Test).

- [ ] **Step 3: Implement overwrite + tag-counts**

Ersetze in `import_.py` die `apply_import`-Funktion komplett durch diese finale Version:

```python
def apply_import(
    db: Session,
    payload: dict[str, Any],
    *,
    mode: str,
) -> dict[str, Any]:
    """Schreibt Import in die DB. Caller ist verantwortlich für Commit/Rollback."""
    if mode not in VALID_MODES:
        raise ImportError(f"invalid mode: {mode!r}")

    entries = payload.get("entries", [])
    incoming_ids = {e["id"] for e in entries if isinstance(e, dict) and "id" in e}
    existing_ids: set[str] = set()
    if incoming_ids:
        rows = db.query(EntryModel.id).filter(EntryModel.id.in_(incoming_ids)).all()
        existing_ids = {r[0] for r in rows}

    # Sammle alle Tag-Namen aus tags[] + entries.tags[] und lege fehlende an
    incoming_tag_names: set[str] = set()
    for t in payload.get("tags", []):
        if isinstance(t, dict) and isinstance(t.get("name"), str):
            incoming_tag_names.add(t["name"])
    for e in entries:
        if isinstance(e, dict):
            for n in e.get("tags", []) or []:
                if isinstance(n, str):
                    incoming_tag_names.add(n)

    existing_tag_names: set[str] = set()
    if incoming_tag_names:
        rows = db.query(TagModel.name).filter(TagModel.name.in_(incoming_tag_names)).all()
        existing_tag_names = {r[0] for r in rows}

    tags_merged = len(existing_tag_names & incoming_tag_names)
    tags_new = len(incoming_tag_names - existing_tag_names)

    for name in incoming_tag_names - existing_tag_names:
        db.add(TagModel(name=name))
    db.flush()

    new_count = 0
    conflict_count = 0
    errors: list[dict[str, Any]] = []

    for idx, raw in enumerate(entries):
        if not isinstance(raw, dict) or "id" not in raw:
            errors.append({"index": idx, "id": None, "reason": "missing id"})
            continue
        eid = raw["id"]
        is_conflict = eid in existing_ids

        try:
            entry_date = _parse_date(raw["entry_date"])
            title = str(raw["title"])
            content = str(raw["content"])
            tags = list(raw.get("tags") or [])
            raw_transcript = raw.get("raw_transcript")
            chat_history = raw.get("chat_history")
            chat_history_json = json.dumps(chat_history) if chat_history else None
        except (KeyError, ValueError) as exc:
            errors.append({"index": idx, "id": eid, "reason": str(exc)})
            continue

        if is_conflict:
            conflict_count += 1
            if mode == "skip":
                continue
            if mode == "copy":
                new_id_val = new_entry_id()
                db.add(EntryModel(
                    id=new_id_val,
                    entry_date=entry_date,
                    title=title,
                    content=content,
                    raw_transcript=raw_transcript,
                    chat_history=chat_history_json,
                ))
                db.flush()
                _set_entry_tags(db, new_id_val, tags)
                continue
            # overwrite
            existing = db.get(EntryModel, eid)
            existing.entry_date = entry_date
            existing.title = title
            existing.content = content
            existing.raw_transcript = raw_transcript
            existing.chat_history = chat_history_json
            existing.updated_at = utc_now()
            existing.embedding = None
            existing.embedding_model = None
            existing.embedding_updated_at = None
            db.flush()
            _set_entry_tags(db, eid, tags)
        else:
            new_count += 1
            db.add(EntryModel(
                id=eid,
                entry_date=entry_date,
                title=title,
                content=content,
                raw_transcript=raw_transcript,
                chat_history=chat_history_json,
            ))
            db.flush()
            _set_entry_tags(db, eid, tags)

    if mode == "skip":
        would_apply = new_count
    else:
        would_apply = new_count + conflict_count

    return {
        "mode": mode,
        "total_in_file": len(entries),
        "new_entries": new_count,
        "conflicts": conflict_count,
        "would_apply": would_apply,
        "tags_new": tags_new,
        "tags_merged": tags_merged,
        "errors": errors,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: PASS (14 Tests total).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/import_.py backend/tests/test_import.py
git commit -m "feat(import): apply_import overwrite + tag counts + error collection"
```

### Task 14: Route `POST /api/import` mit Dry-Run

**Files:**
- Create: `backend/app/routes/import_.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_import.py`

- [ ] **Step 1: Write failing route tests**

Hänge am Ende von `test_import.py` an:

```python
from fastapi.testclient import TestClient
from app.auth.sessions import create_session
from app.main import app

HEADERS = {"x-csrf-token": "t"}
def _cookies(sid): return {"session": sid, "csrf": "t"}


def test_import_requires_auth():
    with TestClient(app) as c:
        r = c.post("/api/import", data={"mode": "skip", "dry_run": "true"})
    assert r.status_code in (401, 403)


def test_import_dry_run_does_not_mutate():
    _clear()
    sid = create_session()
    zip_bytes = _zip_with(_valid_payload())
    with TestClient(app) as c:
        r = c.post(
            "/api/import",
            data={"mode": "skip", "dry_run": "true"},
            files={"file": ("export.zip", zip_bytes, "application/zip")},
            cookies=_cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["total_in_file"] == 1
    assert body["new_entries"] == 1

    with SessionLocal() as db:
        assert db.query(Entry).count() == 0


def test_import_real_run_persists():
    _clear()
    sid = create_session()
    zip_bytes = _zip_with(_valid_payload())
    with TestClient(app) as c:
        r = c.post(
            "/api/import",
            data={"mode": "skip", "dry_run": "false"},
            files={"file": ("export.zip", zip_bytes, "application/zip")},
            cookies=_cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 200
    assert r.json()["dry_run"] is False

    with SessionLocal() as db:
        assert db.query(Entry).count() == 1


def test_import_rejects_invalid_zip():
    _clear()
    sid = create_session()
    with TestClient(app) as c:
        r = c.post(
            "/api/import",
            data={"mode": "skip", "dry_run": "false"},
            files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
            cookies=_cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 400


def test_import_rejects_invalid_mode():
    _clear()
    sid = create_session()
    zip_bytes = _zip_with(_valid_payload())
    with TestClient(app) as c:
        r = c.post(
            "/api/import",
            data={"mode": "nonsense", "dry_run": "false"},
            files={"file": ("export.zip", zip_bytes, "application/zip")},
            cookies=_cookies(sid),
            headers=HEADERS,
        )
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: FAIL (Route existiert noch nicht).

- [ ] **Step 3: Implement route**

```python
# backend/app/routes/import_.py
"""Import-Route: POST /api/import (multipart, dry_run + mode)."""
import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.db import SessionLocal
from app.security.rate_limit import limiter
from app.services.embedding_jobs import request_backfill
from app.services.import_ import (
    ImportError as AppImportError,
    VALID_MODES,
    apply_import,
    parse_export_zip,
    plan_import,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/import")


@router.post("")
@limiter.limit("5/minute")
async def import_zip(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("skip"),
    dry_run: str = Form("false"),
) -> dict:
    if mode not in VALID_MODES:
        raise HTTPException(400, f"invalid mode: {mode}")
    is_dry = dry_run.lower() == "true"

    try:
        blob = await file.read()
        payload = parse_export_zip(blob)
    except AppImportError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        logger.warning("import parse failed: %s", exc)
        raise HTTPException(400, "Import fehlgeschlagen — ZIP prüfen") from exc

    with SessionLocal() as db:
        if is_dry:
            plan = plan_import(db, payload)
            return {
                "dry_run": True,
                "mode": mode,
                **plan,
                "would_apply": _would_apply(plan, mode),
                "errors": [],
            }

        try:
            result = apply_import(db, payload, mode=mode)
            db.commit()
        except AppImportError as exc:
            db.rollback()
            raise HTTPException(400, str(exc)) from exc
        except Exception:
            db.rollback()
            raise

    # Nach overwrite ggf. Backfill anwerfen
    if mode == "overwrite":
        request_backfill()

    return {"dry_run": False, **result}


def _would_apply(plan: dict, mode: str) -> int:
    if mode == "skip":
        return plan["new_entries"]
    return plan["new_entries"] + plan["conflicts"]
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py` nach `from app.routes.export import router as export_router`:

```python
from app.routes.import_ import router as import_router
```

Und nach `app.include_router(export_router)`:

```python
app.include_router(import_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest tests/test_import.py -v`
Expected: PASS (19 Tests total).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/import_.py backend/app/main.py backend/tests/test_import.py
git commit -m "feat(import): POST /api/import with dry-run, modes, rate limit"
```

### Task 15: Frontend — Import-UI in DataPortability

**Files:**
- Modify: `frontend/src/lib/portability.ts`
- Modify: `frontend/src/lib/components/DataPortability.svelte`
- Modify: `frontend/tests/portability.test.ts`

- [ ] **Step 1: Write failing tests for the import client**

Ersetze den Inhalt von `frontend/tests/portability.test.ts` durch:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { exportUrl, importZip, type ImportResult } from "../src/lib/portability";

describe("portability client", () => {
  it("exportUrl returns relative path to export endpoint", () => {
    expect(exportUrl()).toBe("/api/export");
  });

  describe("importZip", () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    it("POSTs multipart with file, mode, dry_run and returns parsed JSON", async () => {
      const mock: ImportResult = {
        dry_run: true, mode: "skip", total_in_file: 3,
        new_entries: 3, conflicts: 0, would_apply: 3,
        tags_new: 1, tags_merged: 0, errors: [],
      };
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true, json: async () => mock, status: 200,
      });
      vi.stubGlobal("fetch", fetchMock);

      const file = new File([new Uint8Array([1, 2, 3])], "export.zip");
      const result = await importZip(file, "skip", true);

      expect(result).toEqual(mock);
      expect(fetchMock).toHaveBeenCalledOnce();
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("/api/import");
      expect(init.method).toBe("POST");
      const body = init.body as FormData;
      expect(body.get("mode")).toBe("skip");
      expect(body.get("dry_run")).toBe("true");
      expect(body.get("file")).toBe(file);
    });

    it("throws on non-OK response", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false, status: 400, json: async () => ({ detail: "bad zip" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      const file = new File([new Uint8Array([0])], "bad.zip");
      await expect(importZip(file, "skip", false)).rejects.toThrow(/bad zip/);
    });
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run tests/portability.test.ts`
Expected: FAIL (importZip existiert nicht).

- [ ] **Step 3: Implement `importZip`**

Ersetze `frontend/src/lib/portability.ts` durch:

```typescript
/** Portabilitäts-API: Export (Download via Anchor-Tag) + Import (multipart POST). */

export type ImportMode = "skip" | "copy" | "overwrite";

export type ImportResult = {
  dry_run: boolean;
  mode: ImportMode;
  total_in_file: number;
  new_entries: number;
  conflicts: number;
  would_apply: number;
  tags_new: number;
  tags_merged: number;
  errors: { index: number; id: string | null; reason: string }[];
};

export function exportUrl(): string {
  return "/api/export";
}

function getCsrf(): string {
  const m = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function importZip(
  file: File,
  mode: ImportMode,
  dryRun: boolean,
): Promise<ImportResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", mode);
  fd.append("dry_run", dryRun ? "true" : "false");

  const resp = await fetch("/api/import", {
    method: "POST",
    body: fd,
    headers: { "x-csrf-token": getCsrf() },
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
    throw new Error(body.detail ?? `HTTP ${resp.status}`);
  }
  return await resp.json();
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run tests/portability.test.ts`
Expected: PASS (3 Tests).

- [ ] **Step 5: Extend DataPortability component with import UI**

Ersetze `frontend/src/lib/components/DataPortability.svelte` durch:

```svelte
<script lang="ts">
  import { exportUrl, importZip, type ImportMode, type ImportResult } from "$lib/portability";

  let file = $state<File | null>(null);
  let mode = $state<ImportMode>("skip");
  let preview = $state<ImportResult | null>(null);
  let importing = $state(false);
  let error = $state<string | null>(null);
  let success = $state<string | null>(null);

  async function onFileChange(ev: Event) {
    const input = ev.target as HTMLInputElement;
    file = input.files?.[0] ?? null;
    preview = null;
    error = null;
    success = null;
    if (!file) return;
    try {
      preview = await importZip(file, mode, true);
    } catch (e) {
      error = `Vorschau fehlgeschlagen: ${(e as Error).message}`;
    }
  }

  async function onModeChange() {
    if (!file) return;
    try {
      preview = await importZip(file, mode, true);
      error = null;
    } catch (e) {
      error = `Vorschau fehlgeschlagen: ${(e as Error).message}`;
    }
  }

  async function runImport() {
    if (!file) return;
    importing = true;
    error = null;
    success = null;
    try {
      const result = await importZip(file, mode, false);
      success =
        `Import abgeschlossen — ${result.new_entries} neu, `
        + `${result.conflicts} Konflikte (Modus: ${result.mode})`;
      preview = result;
    } catch (e) {
      error = `Import fehlgeschlagen: ${(e as Error).message}`;
    } finally {
      importing = false;
    }
  }

  function wouldApplyLabel(p: ImportResult | null, m: ImportMode): string {
    if (!p) return "";
    if (m === "skip") return `${p.new_entries} Einträge werden geschrieben, ${p.conflicts} übersprungen.`;
    if (m === "copy") return `${p.new_entries} neu + ${p.conflicts} als Kopie = ${p.would_apply} Einträge.`;
    return `${p.new_entries} neu + ${p.conflicts} überschrieben = ${p.would_apply} Einträge.`;
  }
</script>

<section class="card">
  <h2>Datenportabilität</h2>

  <div class="block">
    <h3>Export</h3>
    <p class="muted">
      Lade alle Einträge und Tags als ZIP mit <code>entries.json</code> (Format v1) herunter.
    </p>
    <a class="btn" href={exportUrl()} download>Export herunterladen (.zip)</a>
  </div>

  <div class="block">
    <h3>Import</h3>
    <p class="muted">
      Lade ein Export-ZIP hoch. Nach Auswahl siehst du eine Vorschau.
    </p>

    <label class="file-label">
      ZIP wählen
      <input type="file" accept=".zip,application/zip" onchange={onFileChange} />
    </label>

    {#if preview}
      <div class="preview">
        <p><strong>{preview.total_in_file}</strong> Einträge in Datei, davon
          <strong>{preview.new_entries}</strong> neu,
          <strong>{preview.conflicts}</strong> Konflikte,
          <strong>{preview.tags_new}</strong> neue Tags.</p>

        <label>
          Konflikt-Modus:
          <select bind:value={mode} onchange={onModeChange}>
            <option value="skip">Überspringen</option>
            <option value="copy">Als Kopie importieren</option>
            <option value="overwrite">Überschreiben</option>
          </select>
        </label>

        <p class="muted">{wouldApplyLabel(preview, mode)}</p>

        <button
          type="button"
          class="btn"
          onclick={runImport}
          disabled={importing || !file}
        >
          {importing ? "Importiere…" : "Importieren"}
        </button>
      </div>
    {/if}

    {#if error}<p class="error">{error}</p>{/if}
    {#if success}<p class="success">{success}</p>{/if}
  </div>
</section>

<style>
  .card {
    margin: 1rem 0;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .block { margin-bottom: 1rem; }
  .block:last-child { margin-bottom: 0; }
  h3 { margin: 0 0 0.35rem; font-size: 1rem; }
  .muted { color: var(--muted); font-size: 0.9em; margin: 0 0 0.6rem; }
  .btn {
    display: inline-block;
    padding: 0.6rem 1rem;
    min-height: 44px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    text-decoration: none;
    cursor: pointer;
  }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .file-label { display: block; margin: 0.5rem 0; }
  .preview {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: #f3f4f6;
    border-radius: var(--radius);
  }
  .preview select { min-height: 36px; }
  .error { color: #b91c1c; }
  .success { color: #065f46; }
</style>
```

- [ ] **Step 6: Verify and commit**

Run: `cd frontend && npm run check && npx vitest run tests/portability.test.ts`
Expected: keine Typ-Fehler, 3 Tests PASS.

```bash
git add frontend/src/lib/portability.ts frontend/src/lib/components/DataPortability.svelte frontend/tests/portability.test.ts
git commit -m "feat(import): settings UI with dry-run preview + mode selector"
```

### Task 16: Roadmap-Update nach Teil 3

**Files:**
- Modify: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`

- [ ] **Step 1: Ergänze Phase-4-Block**

Hänge an den Phase-4-Block an:

```markdown
- **Import:** services/import_.py (parse_export_zip + plan_import + apply_import mit skip/copy/overwrite + Tag-Merge + Error-Collection). POST /api/import mit dry_run und rate limit 5/min. Overwrite invalidiert Embedding und triggert Backfill. DataPortability-Komponente mit File-Picker, Dry-Run-Preview und Modus-Dropdown.
```

Datum aktualisieren.

---

# Teil 4: Polish-Items

### Task 17: Playwright E2E live — Durchlauf + README-Runbook

**Files:**
- Modify: `README.md`

- [ ] **Step 1: E2E-Live-Lauf manuell ausführen**

```bash
cd frontend
# Backend und Frontend laufen lassen, Seed-User existiert
E2E_LIVE=1 OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.openai.com/v1 npx playwright test
```

Fixe flaky Selektoren / Timing-Probleme, die auftreten. Jede Änderung an `.spec.ts`-Dateien als eigener Commit (`fix(e2e): …`).

- [ ] **Step 2: README-Abschnitt hinzufügen**

In `README.md`, finde den Abschnitt über Tests oder Entwicklung und füge einen neuen Abschnitt ein:

```markdown
## E2E-Tests live ausführen

Die Playwright-Specs sind standardmäßig mit `test.skip(!E2E_LIVE)` gesperrt, weil sie
echte Requests gegen OpenAI-kompatible Endpoints erzeugen (Kosten, Latenz).

**Voraussetzungen:**
- Backend und Frontend laufen lokal (`deploy/docker-compose.yml`).
- Seed-User vorhanden (`APP_PASSWORD` aus `.env`).
- Ein OpenAI-kompatibler Endpoint ist erreichbar.

**Lauf:**
```bash
cd frontend
E2E_LIVE=1 \
  OPENAI_API_KEY=sk-... \
  OPENAI_BASE_URL=https://api.openai.com/v1 \
  npx playwright test
```

**Hinweis:** Live-Läufe verursachen Kosten/Requests gegen den konfigurierten Provider.
Für lokale Entwicklung genügt der Default-Skip.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(e2e): runbook for live Playwright runs"
```

### Task 18: MP3-Concat Live-Validierung — Docstring aktualisieren

**Files:**
- Modify: `backend/app/services/tts.py`

- [ ] **Step 1: Langen Test-Text gegen alternativen TTS-Endpoint abspielen**

Per curl oder `/new`-Flow (Auto-Play) einen Text >1 TTS-Chunk (z.B. 3000 Zeichen Lorem ipsum auf Deutsch) gegen Kokoro oder Piper senden. Manuell abhören: saubere Chunk-Übergänge, keine Knackser.

- [ ] **Step 2: Docstring präzisieren**

Im `services/tts.py`-Docstring den Chunking-Caveat entweder entfernen (wenn sauber) oder durch konkrete Validierungs-Liste ersetzen. Beispiel:

```python
"""TTS-Service: Chunked synthesis für lange Texte.

Chunks werden mit Quote-aware Regex an Satzgrenzen getrennt und MP3-concatenated.
Validiert mit: OpenAI tts-1, Kokoro (af_sarah), Piper. Für andere Server ggf.
Chunking abschalten, falls Übergänge hörbar sind.
"""
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/tts.py
git commit -m "docs(tts): validated chunking with OpenAI + Kokoro + Piper"
```

### Task 19: Roadmap-Update nach Teil 4

**Files:**
- Modify: `/home/julian/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md`

- [ ] **Step 1: Phase 4 als abgeschlossen markieren**

- Entferne „(in Arbeit)" aus dem Phase-4-Titel.
- Verschiebe Phase 4 in `## ✅ Erledigt`.
- Entferne aus `## 📋 Offen`: „Playwright E2E live", „MP3-Concat Live-Test". Lasse „Server-side TTS-Cache" explizit als YAGNI markiert stehen oder entferne ihn ganz.
- Setze `## 🔧 In Arbeit` wieder auf `*(Aktuell nichts — Phase 4 Polish & Portabilität abgeschlossen.)*`.
- Datum aktualisieren.

Beispiel für neuen Phase-4-Block:

```markdown
### Phase 4 Polish & Portabilität (`v0.4.0-polish`)
- **Pagination /entries:** Load-More-Button (Page-Size 50), mergePage/hasMore-Helper, Filter/Suche resetten die Liste, semantische Suche umgeht Pagination.
- **Export:** services/export.py (build_export_payload + stream_export_zip), GET /api/export streamt ZIP mit entries.json (Format v1), Settings-Komponente DataPortability mit Download-Button.
- **Import:** services/import_.py (parse_export_zip + plan_import + apply_import mit skip/copy/overwrite + Tag-Merge + Error-Collection). POST /api/import mit dry_run und rate limit 5/min. Overwrite invalidiert Embedding und triggert Backfill. DataPortability-Komponente mit File-Picker, Dry-Run-Preview und Modus-Dropdown.
- **Polish:** Playwright-Live-Runbook in README, MP3-Concat validiert mit OpenAI tts-1, Kokoro, Piper.
```

---

# Abschluss

### Task 20: Gesamt-Verifikation

- [ ] **Step 1: Alle Backend-Tests laufen**

Run: `cd backend && .venv/bin/pytest -q`
Expected: alle Tests grün (erwartet ~170, war 151 vor Phase 4).

- [ ] **Step 2: Alle Frontend-Tests laufen**

Run: `cd frontend && npm test && npm run check`
Expected: alle Tests grün, keine Typ-Fehler.

- [ ] **Step 3: Full-Stack Smoke-Test im Browser**

```bash
docker compose -f deploy/docker-compose.yml down
docker compose -f deploy/docker-compose.yml up -d --build
```

Durchlaufen:
- Login.
- `/entries` mit >50 Einträgen: Load-More funktioniert, Filter/Suche resetten.
- `/settings` → Export herunterladen, ZIP enthält `entries.json` mit Einträgen.
- `/settings` → dieselbe ZIP wieder hochladen, Dry-Run zeigt korrekte Zahlen, Modus-Wechsel aktualisiert Preview, Import mit `overwrite` läuft durch.
- Nach Import: semantische Suche triggert Backfill (Status in `/settings` beobachten).

Keine automatisierbaren Regression-Tests fehlen, wenn alles läuft.

- [ ] **Step 4: Roadmap final prüfen und Session-Ende**

Memory-Datei nochmal gegenchecken — Phase 4 sauber als „Erledigt" markiert? Datum korrekt?

---

## Zusammenfassung

- **20 Tasks**, ~120 kleine Steps.
- Kritische TDD-Punkte: Alle Backend-Services (export.py, import_.py) und `importZip`-Client.
- Pagination und Settings-Integration sind primär UI-Arbeit mit leichtem Test-Anteil.
- Polish-Items erzeugen keine neuen Tests (nur Doku + manuelle Validierung).
- Jeder Teil endet mit einem Roadmap-Update (Memory-Datei).
