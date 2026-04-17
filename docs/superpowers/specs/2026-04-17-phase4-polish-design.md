# Phase 4 — Polish & Portabilität (Design)

**Datum:** 2026-04-17
**Version:** `v0.4.0-polish`
**Branch:** `main` (keine Feature-Branches, wie im Projekt üblich)

## Ziele

Die OSS-Portabilität des journalAI-Speichers herstellen (Export + Import mit Konflikt-Modi) und `/entries` skalierbar machen. Parallel zwei aufgeschobene Polish-Items einmal live gegenprüfen.

## Scope

**Drin:**
1. **Export** — `GET /api/export` streamt ein ZIP mit versionierter `entries.json`.
2. **Import** — `POST /api/import` akzeptiert dasselbe Format; Dry-Run + drei Konflikt-Modi (`skip`/`copy`/`overwrite`).
3. **Pagination `/entries`** — „Mehr laden"-Button, Page-Size 50.
4. **Polish** — Playwright-Live-Durchlauf + Runbook, MP3-Concat-Live-Validierung gegen nicht-OpenAI-Endpoint.

**Raus (YAGNI):**
- Server-side TTS-Cache (kein Memory-Druck gemeldet).
- Import aus Fremdformaten (Day One, Obsidian, JSON-Feed).
- Reichhaltiges Export-UI (Progress, inkrementelles Streaming, Selektion nach Datum/Tag).
- Export/Import von Embeddings (werden beim nächsten Indexlauf ohnehin neu erzeugt).
- Export von User/Auth/Settings (per-Instanz-spezifisch, nicht portabel).

---

## 1. Export

### API

```
GET /api/export
Response: application/zip
Content-Disposition: attachment; filename="journalai-export-YYYY-MM-DD.zip"
```

- Auth-geschützt (Session-Cookie), CSRF wie bei anderen Mutationen nicht nötig (GET).
- Kein explizites Rate-Limit — Aktion ist selten und auth-gated.
- Streamt via `fastapi.responses.StreamingResponse` mit einem `zipfile.ZipFile(..., ZIP_DEFLATED)`.

### ZIP-Inhalt

Eine Datei: `entries.json`. Kein Manifest, kein zusätzlicher Ordner — KISS.

### JSON-Schema (`version: "1"`)

```json
{
  "version": "1",
  "exported_at": "2026-04-17T10:00:00Z",
  "app": "journalAI",
  "entries": [
    {
      "id": "uuid-string",
      "entry_date": "YYYY-MM-DD",
      "title": "string",
      "content": "string (markdown)",
      "tags": ["tagname1", "tagname2"],
      "raw_transcript": "string | null",
      "chat_history": [{...}] ,
      "created_at": "ISO-8601 UTC",
      "updated_at": "ISO-8601 UTC"
    }
  ],
  "tags": [
    { "name": "tagname1" },
    { "name": "tagname2" }
  ]
}
```

- `entries` enthalten die Tags als Liste von Namen (einfach zu lesen, kein Joining nötig).
- `tags[]` ist die kanonische Tag-Liste (inkl. Tags ohne aktuelle Einträge, falls es sie gibt — in der Praxis werden leere Tags beim Delete entfernt, aber wir serialisieren den tatsächlichen DB-Stand).
- **Nicht enthalten:** Embedding-Blobs, User/Auth/Settings, Session-State.

### Backend

- Neues Modul `backend/app/services/export.py`:
  - `build_export_payload(db) -> dict` (reiner Builder, testbar ohne Streaming).
  - `stream_export_zip(db) -> Iterator[bytes]` (wrappt den Dict in ein In-Memory-ZIP).
- Neue Route `backend/app/routes/export.py` (`GET /api/export`).
- Registrierung in `main.py`.

### Frontend

- In `/settings` ein neuer Abschnitt **„Datenportabilität"**:
  - Export-Button „Export herunterladen (.zip)".
  - Klick triggert Download via temporärem `<a href download>` (oder `fetch` + `Blob` + `URL.createObjectURL`, je nachdem was CSRF-kompatibel bleibt — GET ist hier einfach).
- Kein Progress-UI, keine Spinner-Logik im ersten Wurf (Export ist typischerweise in <1s durch).

### Tests

- Backend (pytest):
  - Export bei leerer DB → ZIP mit `entries: [], tags: []`, Schema-Felder vorhanden.
  - Export mit Einträgen, Tags, `raw_transcript`, `chat_history` → roundtrip-fähig.
  - ZIP enthält genau eine Datei `entries.json`.
  - `entry_date` als ISO-Date-String, `created_at`/`updated_at` als ISO-DateTime-UTC.
- Frontend (Vitest):
  - Export-Button ist sichtbar, triggert `GET /api/export` (mocked).

---

## 2. Import

### API

```
POST /api/import
Content-Type: multipart/form-data
Fields:
  file:     Upload (ZIP im Export-Format)
  mode:     "skip" | "copy" | "overwrite"
  dry_run:  "true" | "false"  (Default "false")
Response: application/json (s.u.)
```

- Auth + CSRF (Double-Submit wie alle Mutationen).
- Rate-Limit: **5/min** (Import invalidiert u.U. viele Embeddings, triggert Backfill).

### Response-Format

```json
{
  "dry_run": true,
  "mode": "skip",
  "total_in_file": 42,
  "new_entries": 38,
  "conflicts": 4,
  "would_apply": 38,
  "tags_new": 2,
  "tags_merged": 7,
  "errors": [
    { "index": 17, "id": "uuid", "reason": "invalid entry_date" }
  ]
}
```

- Gleiches Format für Dry-Run und echten Import; im echten Lauf spiegeln die Zahlen den tatsächlichen Effekt wider.
- `would_apply` = Einträge, die bei diesem Modus geschrieben würden.
  - `skip`: `new_entries`
  - `copy`: `new_entries + conflicts` (Konflikte werden als Kopie angelegt)
  - `overwrite`: `new_entries + conflicts`

### Konflikt-Modi (bei ID-Match)

| Modus | Verhalten |
|---|---|
| `skip` | Bestehenden Eintrag unverändert lassen, importierte Version verwerfen. |
| `copy` | Neue UUID vergeben, `created_at = now()`, Rest 1:1 übernehmen. Kein Konflikt mehr. |
| `overwrite` | Bestehenden Eintrag in allen Feldern ersetzen (`title`, `content`, `entry_date`, `tags`, `raw_transcript`, `chat_history`), `updated_at = now()`, **Embedding invalidieren** (Backfill-Worker greift automatisch). |

### Tag-Merge

- Modus-unabhängig: Tags werden per `name` gematcht, fehlende angelegt.
- Bei `overwrite` wird die Tag-Liste eines Eintrags komplett durch die importierte ersetzt.
- Bei `skip` bleiben die bestehenden Entry-Tags unberührt.
- Bei `copy` erhält der neue Eintrag die importierten Tags.

### Validierung & Fehlerverhalten

- ZIP muss genau `entries.json` enthalten → sonst 400.
- `version` muss `"1"` sein → sonst 400 mit klarer Message.
- Pro-Entry-Fehler (z.B. invalides Datum, Titel zu lang): in `errors[]` sammeln, Import der validen Einträge läuft weiter.
- Harte Fehler (defekte JSON, unlesbares ZIP): 400, keine DB-Mutation.
- **Atomarität:** Eine SQLAlchemy-Transaktion um den gesamten Import. Commit erst am Ende. Bei harten Fehlern Rollback.
- **Dry-Run:** Transaktion läuft durch, wird am Ende **immer** zurückgerollt. Response-Zahlen sind dieselben wie beim echten Lauf.

### Backend

- Neues Modul `backend/app/services/import_.py` (Unterstrich, weil `import` reserved):
  - `parse_export_zip(upload) -> ExportPayload` (Validierung + Parsing).
  - `plan_import(db, payload, mode) -> ImportPlan` (berechnet `new_entries`, `conflicts`, `tags_new`, `tags_merged` ohne zu schreiben).
  - `apply_import(db, payload, plan, mode) -> ImportResult` (führt Schreib-Operationen aus, invalidiert Embeddings bei `overwrite`).
- Neue Route `backend/app/routes/import_.py` (`POST /api/import`).
- **Embedding-Invalidierung bei `overwrite`:** `entry.embedding = None`, `entry.embedding_model = None`, `entry.embedding_updated_at = None`. Worker picked das via Backfill auf.

### Frontend

- In `/settings`, gleicher Abschnitt „Datenportabilität", nach dem Export-Button:
  - File-Input (`<input type="file" accept=".zip">`).
  - Nach Auswahl: automatischer `POST /api/import` mit `dry_run=true, mode=skip` (Default für Preview).
  - Preview-Box zeigt Zahlen: „42 Einträge in Datei, 38 neu, 4 Konflikte, 2 neue Tags".
  - Modus-Dropdown („Überspringen" / „Als Kopie importieren" / „Überschreiben") — ändert den Text „Mit diesem Modus würden X Einträge angewendet".
  - „Importieren"-Button (disabled bis Datei + Modus gewählt).
  - Bei Erfolg: Toast „Import abgeschlossen: X neu, Y Kopien, Z überschrieben" + Navigation zurück nach `/entries`.
  - Fehler (z.B. invalides ZIP): Inline-Fehlermeldung im Import-Bereich.

### Tests

- Backend:
  - Dry-Run auf leerer DB: `new_entries = total_in_file`, `conflicts = 0`, keine DB-Mutation.
  - Dry-Run mit bestehender DB: korrekte `conflicts`-Zahl.
  - Import `skip`: Konflikte bleiben unverändert, neue Einträge werden geschrieben.
  - Import `copy`: Konflikte werden als neue Einträge angelegt (andere ID, neue `created_at`).
  - Import `overwrite`: Konflikte werden ersetzt, `embedding = None` nach Import.
  - Tag-Merge: fehlende Tags angelegt, bestehende wiederverwendet (kein Duplikat).
  - Defektes ZIP → 400.
  - Falsche Version → 400.
  - Einzelner Entry mit invalidem Datum → `errors[]` enthält ihn, valide Einträge werden importiert.
  - Atomarität: Hartfehler im 2. Write → 1. Write ist zurückgerollt.
  - Rate-Limit greift.
- Frontend (Vitest):
  - File-Picker → Dry-Run → Preview zeigt korrekte Zahlen.
  - Modus-Wechsel aktualisiert `would_apply`-Text.
  - Importieren-Button disabled ohne Datei.

---

## 3. Pagination `/entries`

### Backend

- `GET /api/entries` liefert bereits `{ total: int, items: Entry[] }` — keine Server-Änderung nötig. Der Client nutzt `total` für den „Mehr laden"-Button.

### Frontend

- `/entries/+page.svelte`:
  - State: `entries: Entry[]`, `offset = 0`, `total = 0`, `loading = false`, `hasMore = false`.
  - Initial `GET /api/entries?limit=50&offset=0` → setzt `entries`, `total`, `hasMore = entries.length < total`.
  - „Mehr laden"-Button unter der Liste, sichtbar wenn `hasMore`, disabled während `loading`.
  - Klick → `GET ?limit=50&offset=entries.length` → appendet.
  - **Filter/Suche** (Tag-Filter, Volltext-Suche): resettet `offset = 0`, `entries = []`, neu laden.
  - **Semantische Suche:** Bleibt unpaginiert (liefert Top-N, meist ≤20). „Mehr laden" in diesem Modus ausgeblendet.
  - Optional: Listen-Header „Einträge 1–50 von 137" (nice-to-have, nicht kritisch).

### Tests

- Backend: `?limit=50&offset=0` und `?limit=50&offset=50` liefern disjunkte Sets; `total` stimmt.
- Frontend (Vitest):
  - Mehr-Laden appendet statt zu ersetzen.
  - Filter-Wechsel resettet Liste.
  - `hasMore = false` blendet Button aus.
  - Im semantischen Such-Modus ist der Button nicht sichtbar.

---

## 4. Polish-Items

### Playwright E2E live

- Einmaliger Durchlauf aller Skeletons mit `E2E_LIVE=1` gegen einen echten OpenAI-kompatiblen Endpoint (lokaler Server oder OpenAI direkt).
- Erwartete Arbeit: flaky Selektoren fixen, SSE-Timing justieren, etwaige Selektor-Drifts seit Phase 2/3 ausbügeln.
- **Deliverable:** README-Abschnitt `## E2E-Tests live ausführen` mit:
  - Benötigten Env-Vars (`E2E_LIVE`, `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`).
  - Setup-Schritten (Backend + Frontend hoch, Seed-User).
  - Kommando zum Starten (`npm run test:e2e` o.ä.).
  - Hinweis, dass der Lauf Kosten/Requests gegen den Provider erzeugt.

### MP3-Concat Live-Validierung

- Langer Text (>1 TTS-Chunk, z.B. 3000 Zeichen) gegen einen nicht-OpenAI-Endpoint — primär **Kokoro** oder **Piper**, falls lokal verfügbar.
- Output manuell abspielen: Saubere Übergänge, keine Knackser, keine Doppelungen.
- **Deliverable:** Docstring in `services/tts.py` präzisieren — entweder Caveat **entfernen**, wenn sauber, oder als Liste validierter Endpoints fixieren (`Validated with: OpenAI tts-1, Kokoro, Piper`).

### Keine Unit-Tests für diese Items

- Ziel der Polish-Items ist **Live-Verifikation**, nicht neue automatisierte Abdeckung. Neue Tests entstehen nur, wenn der Live-Lauf Bugs findet, die regressionsanfällig sind.

---

## 5. CI & Deployment

- Keine CI-Änderungen (Tests laufen in bestehender Pipeline).
- Kein Release-Versionssprung-Aufwand (semantic versioning zieht `0.4.0` automatisch nach, sobald ein Tag gesetzt wird — Tag-Setzen ist out-of-scope dieser Phase).
- Docker Compose unverändert.

---

## 6. Reihenfolge & Risiken

**Empfohlene Implementierungsreihenfolge:**

1. **Pagination** (kleinstes Delta, liefert sofort Mehrwert bei >50 Einträgen).
2. **Export** (Basis für Import, testbar ohne Import).
3. **Import** (braucht Export-Format als Input, hat die meiste Logik).
4. **Polish-Items** (unabhängig, zum Abschluss).

**Risiken:**

- **SQLCipher-Transaktionen + Dry-Run-Rollback:** Muss in Tests verifiziert werden, dass ein expliziter `db.rollback()` im Dry-Run wirklich alles zurücksetzt (Tags inklusive).
- **Embedding-Invalidierung bei Overwrite-Import:** Der Backfill-Worker muss die invalidierten Einträge aufgreifen — gegebenenfalls `trigger_backfill_check()` explizit nach Import-Commit aufrufen.
- **ZIP-Streaming im SvelteKit-SPA:** `<a href download>` reicht in der Regel, kein `fetch`-Blob-Workaround nötig, solange der GET keinen CSRF-Token braucht (GET ist safe-method).
- **`total`-Count-Breaking-Change:** Aktuell liefert `GET /api/entries` vermutlich ein Array. Wechsel auf `{ entries, total }` betrifft nur den einen Frontend-Call, ist trotzdem sauber zu dokumentieren.

---

## 7. Deliverables

- **Backend:**
  - `services/export.py`, `routes/export.py`
  - `services/import_.py`, `routes/import_.py`
  - Anpassung `GET /api/entries` auf `{ entries, total }`-Response
  - ~15–20 neue Backend-Tests

- **Frontend:**
  - `/settings` — Abschnitt „Datenportabilität" (Export + Import inkl. Dry-Run-Preview)
  - `/entries` — „Mehr laden"-Button + Pagination-Store-Logik
  - ~6–8 neue Frontend-Tests

- **Docs:**
  - README-Abschnitt „E2E live ausführen"
  - Aktualisiertes `services/tts.py`-Docstring
  - `docs/superpowers/specs/2026-04-17-phase4-polish-design.md` (dieses Dokument)
  - `docs/superpowers/plans/2026-04-17-phase4-polish.md` (folgt aus `writing-plans`)

**Geschätzt insgesamt:** 5–7 h aktive Arbeit.
