# Semantic Search — Design Spec

**Datum:** 2026-04-17
**Phase:** 2 (nach MVP v0.1.0 + TTS v0.2.0)
**Status:** Approved Design — bereit für Implementation-Plan

## 1. Ziel & Nutzungsszenario

journalAI soll eine semantische Suche bekommen, die es erlaubt, natürlichsprachliche Queries (getippt oder per Voice diktiert) über alle Journal-Einträge laufen zu lassen und die inhaltlich passendsten Einträge zurückzubekommen — auch wenn die exakten Suchbegriffe nicht in den Einträgen stehen.

**Leit-Szenario:** Auf `/entries` sitzt ein Suchfeld. Der Nutzer diktiert:

> „Hey, ich habe doch mal darüber gesprochen, dass ich einen Traum mit Regenbögen hatte. Zeig mir die entsprechenden Einträge."

Das System extrahiert die Kernabsicht, findet ähnliche Einträge per Vektor-Retrieval, lässt ein LLM die Top-Kandidaten re-ranken, und zeigt Top-10 mit einer kurzen Begründung pro Treffer, warum der Eintrag passt.

**Nicht-Ziele in dieser Phase:**
- Related-Entries-Feature auf der Detailseite (könnte später als Bonus kommen, aber nicht Teil dieser Spec).
- Hybrid-Ranking, das Keyword- und Semantik-Ergebnisse automatisch mischt.
- sqlite-vec oder andere native Vektor-DB-Integration (bewusst zugunsten eines einfachen BLOB-Ansatzes verworfen).

## 2. Architektur-Entscheidungen (kompakt)

| Entscheidung | Wahl | Begründung |
|---|---|---|
| Query-Verarbeitung | LLM-Intent-Extract **+** LLM-Re-Ranking | Konversationelle Queries robust machen, Top-Treffer bewusst bewerten |
| Verhältnis zu Keyword-Suche | Toggle Keyword ↔ Semantik | User entscheidet selbst zwischen „explore" und „lookup", einfachste robuste Lösung |
| Embedding-Quelle | nur `title + content` | `content` ist bereits die LLM-kuratierte Version; weniger Migration-/Invalidation-Risiko |
| Vektor-Storage | BLOB-Spalte pro Eintrag + numpy Cosine | SQLCipher-freundlich, null neue C-Dependencies, skaliert bis ~10k Einträgen locker |
| Embedding-Lifecycle | async beim Save + Backfill beim Serverstart | Keine Save-Latenz, keine manuellen Knöpfe für den Normalfall |
| Modellwechsel | `embedding_model` pro Eintrag **+** explizit User-Dialog bei Mismatch | Transparenz + Kontrolle statt silent re-index |
| Such-UI | Liste mit LLM-Begründung pro Treffer, Top-10 Default | Nutzen des Re-Rankings sichtbar machen |

## 3. Datenmodell & Migrationen

### 3.1 Entry-Model (`backend/app/models/entry.py`)

Drei neue Spalten:

| Spalte | Typ | Nullable | Zweck |
|---|---|---|---|
| `embedding` | `LargeBinary` | Ja | Packed float32-numpy-Array (z.B. 1536-dim → 6144 Bytes) |
| `embedding_model` | `String` | Ja | Modell-Name, z.B. `"text-embedding-3-small"` — dient zur Kompatibilitäts-Prüfung |
| `embedding_updated_at` | `DateTime` | Ja | Zeitpunkt des letzten Embeddings, für Debug/Inspektion |

Alle nullable, damit die Migration auf Bestands-DBs läuft und Backfill schrittweise nachholen kann.

### 3.2 AppSettings (`backend/app/models/settings.py`)

Die `embed`-Capability existiert bereits (`embed_base_url`, `embed_model`, `embed_api_key_wrapped`). Neu:

| Spalte | Typ | Nullable | Zweck |
|---|---|---|---|
| `embed_dimensions` | `Integer` | Ja | Wird beim ersten erfolgreichen Embed gefüllt, als Konsistenz-Check beim Dimension-Mismatch |

### 3.3 Alembic-Migration

Eine einzige neue Revision, die drei `op.add_column`-Aufrufe auf `entries` und einen auf `settings` ausführt. Alle nullable. Kein Daten-Rewrite nötig.

### 3.4 Dependencies

- `numpy` neu in `backend/requirements.txt`. Wird für Vektor-Packing (`pack_vector`/`unpack_vector`) und vektorisierte Cosine-Similarity gebraucht.
- Keine weiteren C-Libraries.

## 4. Backend-Komponenten

### 4.1 `backend/app/services/embeddings.py` (neu)

```
embed_text(text: str) -> tuple[np.ndarray, str]
    → ruft embed-Capability (OpenAI-kompatibel), gibt (vector, model_name) zurück.
    → 502-Mapping analog services/tts.py (401/404/5xx/ConnectError).

pack_vector(vec: np.ndarray) -> bytes
    → float32-Serialisierung via np.asarray(..., dtype=np.float32).tobytes().

unpack_vector(blob: bytes) -> np.ndarray
    → np.frombuffer(blob, dtype=np.float32).

cosine_similarity(query_vec: np.ndarray, candidate_matrix: np.ndarray) -> np.ndarray
    → vektorisiert: (Q · M.T) / (|Q| · |Mᵢ|). Arbeitet auf der gesamten Kandidaten-Matrix auf einmal.

build_entry_text(entry: Entry) -> str
    → kanonische Form: f"{entry.title}\n\n{entry.content}".
    → Gekürzt auf max ~7000 Tokens via chars/4-Heuristik (~28000 Zeichen). Sicherheitsnetz für Extremfälle.
```

### 4.2 `backend/app/services/search.py` (neu)

```
extract_search_intent(query: str) -> str
    → Mini-Call an chat-Capability (low temperature, max 60 Tokens).
    → System-Prompt-Konstante SEARCH_INTENT_PROMPT im Modul.
    → Erwartete Reduktion: "Hey, ich habe doch mal..." → "Traum mit Regenbögen".
    → Fallback bei Fehler: Rückgabe der Original-Query (graceful degradation).

rerank_results(query: str, candidates: list[Entry], top_k: int) -> list[RerankedResult]
    → Call an chat-Capability im JSON-Mode.
    → System-Prompt: Erklärt Format [{id, score (0-100), reason (max 120 Zeichen)}].
    → Candidate-Payload: id + title + content-Excerpt (erste ~300 Zeichen).
    → Fallback: wenn JSON kaputt oder Call scheitert → reines Cosine-Ranking, reason=None.

semantic_search(query: str, top_k: int = 10) -> SemanticSearchResponse
    1. intent = extract_search_intent(query)
    2. query_vec, _ = embed_text(intent)
    3. SELECT id, title, content, embedding FROM entries
       WHERE embedding IS NOT NULL AND embedding_model = current_settings.embed_model
    4. scores = cosine_similarity(query_vec, stacked_candidate_matrix)
    5. Top-30 nach cosine-score → rerank_results(query, top30, top_k) → Top-10
    6. Return {results, status: "ok"|"indexing", progress: {embedded, total}}
```

`SemanticSearchResponse`:

```python
class RerankedResult(BaseModel):
    entry_id: str
    title: str
    excerpt: str        # erste ~200 Zeichen content
    score: float        # 0-100, aus Re-Rank oder Cosine*100 als Fallback
    reason: str | None  # None wenn Rerank-Fallback

class SemanticSearchResponse(BaseModel):
    results: list[RerankedResult]
    status: Literal["ok", "indexing", "not_configured"]
    progress: dict | None  # {"embedded": int, "total": int} wenn indexing
```

### 4.3 `backend/app/services/embedding_jobs.py` (neu)

```
embed_entry_async(entry_id: str) -> None
    → FastAPI BackgroundTask.
    → Re-lädt Entry aus DB (könnte inzwischen gelöscht sein → skip).
    → build_entry_text → embed_text → pack_vector.
    → UPDATE entries SET embedding=?, embedding_model=?, embedding_updated_at=NOW() WHERE id=?.
    → Bei Fehler: Log-Warning, Entry bleibt embedding=NULL. Kein Retry im Task.
    → Prüft nach Embed-Call nochmal Existenz, um Race mit DELETE zu vermeiden.

backfill_missing_embeddings() -> None
    → asyncio.Lock (Modul-global) verhindert parallele Läufe.
    → SELECT id FROM entries
      WHERE embedding IS NULL OR embedding_model != current_settings.embed_model
      ORDER BY updated_at DESC
    → For-each mit 200ms sleep zwischen Calls.
    → Bei 429: exponential backoff 1s/2s/4s, max 3 Retries, dann skip.
    → Keine Exceptions propagieren — jeder Entry ist unabhängig.

reindex_all() -> None
    → UPDATE entries SET embedding=NULL, embedding_model=NULL, embedding_updated_at=NULL.
    → Dann backfill_missing_embeddings() aufrufen.
```

Startup-Integration: im FastAPI-`lifespan`-Hook wird `asyncio.create_task(backfill_missing_embeddings())` gestartet (non-blocking).

### 4.4 Neue Routen — `backend/app/routes/search.py`

| Methode + Pfad | Body/Query | Response | Auth | Rate-Limit |
|---|---|---|---|---|
| `POST /api/search` | `{query: str, top_k?: int=10}` | `SemanticSearchResponse` | Session + CSRF | 30/min pro Session |
| `GET /api/search/status` | — | `{total, embedded, pending, current_model, configured: bool, indexing: bool}` | Session | — |
| `POST /api/search/reindex` | — | `202 Accepted` oder `409 Conflict` | Session + CSRF | 1/min |

### 4.5 Modellwechsel-Erkennung in Settings-PUT

`backend/app/routes/settings.py` wird erweitert: Wenn der PUT den Wert von `embed_model` ändert **und** `SELECT COUNT(*) FROM entries WHERE embedding_model IS NOT NULL AND embedding_model != <neu>` > 0 ist, enthält die Response zusätzlich:

```json
{
  ...existing settings payload...,
  "warning": "embedding_model_mismatch",
  "embedding_mismatch": {
    "old_model": "...",
    "new_model": "...",
    "affected_entries": 42
  }
}
```

Der Settings-Wert wird gespeichert — die Inkompatibilität ist sichtbar, aber nicht blockierend. Frontend zeigt daraufhin den Modellwechsel-Dialog (siehe 5.3).

### 4.6 Entry-Routen-Anpassungen

`POST /api/entries` und `PATCH /api/entries/{id}`:

- Nach erfolgreichem DB-Insert/Update prüfen, ob `title` **oder** `content` sich verändert haben (bei Create: immer ja).
- Wenn ja: `embedding=NULL`, `embedding_model=NULL`, `embedding_updated_at=NULL` setzen, dann `BackgroundTasks.add_task(embed_entry_async, entry.id)`.
- Wenn nein (nur Tags/Datum/raw_transcript/chat_history geändert): Embedding unangetastet, kein LLM-Call.

`DELETE /api/entries/{id}`: keine Änderung nötig. Der BLOB-Eintrag geht automatisch mit der Zeile weg.

## 5. Frontend-Komponenten

### 5.1 `/entries`-Seite — Such-UI

Vorhandenes Suchfeld wird erweitert um:

- **Toggle "Stichwort ↔ Semantisch"** — ARIA-switch links neben dem Input. Default: Stichwort (bestehendes Verhalten). Wechsel ruft anderen Endpoint.
- **Mikrofon-Button** im Input — nur im Semantik-Modus sichtbar. Nutzt denselben Recorder-Flow wie `/new`: Aufnahme → `POST /api/transcribe` → Transkript als Query einfügen (User kann noch editieren vor dem Send).
- **Submit** im Semantik-Modus: `POST /api/search` mit Spinner + Hinweis „Suche dauert einen Moment …" (Latenz ~2-3 s wegen Intent+Embed+Rerank).

### 5.2 Ergebnis-Darstellung

Eigene `SearchResultList`-Komponente (statt der Entry-List-Component), weil die Darstellung abweicht:

- Pro Treffer: Titel, 200-Zeichen-Excerpt, Datum, Relevanz-Score als kleines Badge (z.B. `94`), **Reason-Zeile unter dem Excerpt** (wenn vorhanden) in kleinerer, leicht gedämpfter Schrift.
- Click auf Card → `/entries/{id}` (normale Detailseite).
- Bei `status: "indexing"` → Placeholder-Banner oben: „Index wird gebaut … {embedded} von {total}". Keine Results zeigen, aber Status periodisch (alle 3 s) via `GET /api/search/status` aktualisieren.
- Bei `status: "not_configured"` → Info-Banner mit Link zu /settings.

### 5.3 Modellwechsel-Dialog

Neue Komponente `ModelMismatchDialog.svelte`, getriggert durch den `warning: "embedding_model_mismatch"` in der Settings-PUT-Response.

Inhalt:

> **Embedding-Modell geändert**
>
> Deine bisherigen {affected_entries} Einträge wurden mit `{old_model}` indexiert. Du hast jetzt `{new_model}` gewählt. Die Modelle sind untereinander nicht kompatibel — semantische Suche funktioniert nur auf Einträgen im aktuellen Modell.
>
> Was möchtest du tun?
>
> **[Zurück zum alten Modell]** &nbsp; **[Neu indexieren]** &nbsp; **[Später entscheiden]**

- **Zurück zum alten Modell** → `PUT /api/settings {embed_model: old_model}`, Dialog schließt.
- **Neu indexieren** → Confirm („Alle {total} Einträge werden neu berechnet, Dauer ~{total * 0.3}s") → `POST /api/search/reindex` → Dialog schließt → kleiner Progress-Indikator in der Topbar, pollt `/api/search/status`.
- **Später entscheiden** → Dialog schließt, persistentes Warn-Banner in `/entries` und `/settings`: „Embedding-Modell ist inkonsistent. Klicke hier, um zu entscheiden." (öffnet Dialog neu).

### 5.4 Settings-UI-Erweiterung

- Kleiner Status-Block im Embed-Settings-Bereich: „{embedded} von {total} Einträgen indexiert" mit optionalem „Jetzt neu indexieren"-Button (der auch ohne Modellwechsel funktioniert, für den Fall dass man manuell triggern will).

### 5.5 API-Client (`frontend/src/lib/`)

Neue Datei `search.ts`:

```ts
export async function searchEntries(query: string, topK = 10): Promise<SemanticSearchResponse>
export async function getSearchStatus(): Promise<SearchStatus>
export async function reindexEmbeddings(): Promise<void>
```

Alle mit CSRF-Header, folgt dem bestehenden `api<T>()`-Pattern in `frontend/src/lib/api.ts`.

### 5.6 Search-Store (`frontend/src/lib/stores/search.ts`)

Svelte-5-runes-Store mit:

- `query: string`
- `mode: "keyword" | "semantic"`
- `loading: boolean`
- `results: RerankedResult[] | null`
- `status: SearchStatus | null` (für Indexing-Banner)

Actions: `setQuery`, `setMode`, `runSearch`, `pollStatus`.

## 6. Datenfluss (End-to-End)

### 6.1 Eintrag erstellen / editieren

```
POST /api/entries (create)           PATCH /api/entries/{id} (content changed)
        │                                    │
        ├─ DB-Insert commit                  ├─ Content/Title diff?
        │                                    │      │
        │                                    │      └─ Ja → embedding/embedding_model = NULL
        │                                    │
        └─ BackgroundTask: embed_entry_async(id)
                 │
                 ├─ Re-load Entry (skip wenn weg)
                 ├─ build_entry_text → embed_text → pack_vector
                 └─ UPDATE entries SET embedding=?, embedding_model=?, embedding_updated_at=NOW()
                    (Pre-write Existence-Check gegen Race mit DELETE)
```

### 6.2 App-Startup

```
FastAPI lifespan → asyncio.create_task(backfill_missing_embeddings())
        │
        └─ Lock acquire (non-blocking für HTTP-Server)
                │
                ├─ SELECT entries WHERE embedding IS NULL OR embedding_model != current
                └─ Sequential: embed_text + UPDATE (200ms Pause, 429-Backoff)
```

### 6.3 Semantische Suche

```
POST /api/search {query: "Hey habe doch mal Regenbogen-Traum"}
        │
        ├─ 1. extract_search_intent → "Traum mit Regenbögen"       (~300ms)
        ├─ 2. embed_text(intent) → query_vec                        (~200ms)
        ├─ 3. Kandidaten-Batch laden (embedding_model = current)
        │     → Dimension-Mismatch-Safe: WHERE-Filter
        ├─ 4. cosine_similarity → sortieren → Top-30
        ├─ 5. rerank_results → Top-10                               (~1-2s)
        └─ Response: SemanticSearchResponse
```

Gesamtlatenz ~2-3 s. Frontend zeigt Spinner mit Hinweistext.

### 6.4 Eintrag editieren

- `PATCH` ändert Content/Title → Backend nullt Embedding-Felder, BackgroundTask neu embedden.
- `PATCH` ändert nur Tags/Datum → Embedding bleibt. Kein LLM-Call.
- Zwischen Save und Re-Embed ist der Eintrag kurz nicht semantisch findbar (Keyword-Suche bleibt unverändert funktional).

### 6.5 Eintrag löschen

- `DELETE` auf `/api/entries/{id}` → Zeile weg → Embedding-BLOB automatisch mit weg. Kein separater Cleanup.
- Race-Fall: laufender Background-Embed wird durch Pre-write Existence-Check abgefangen.

### 6.6 Modellwechsel

```
PUT /api/settings {embed_model: "neues-modell"}
        │
        ├─ Ändert embed_model? → Count existierende Einträge mit abweichendem Modell
        │
        ├─ > 0 → Response enthält warning + embedding_mismatch-Payload
        │       (Settings-Wert wird trotzdem gespeichert)
        │
        └─ Frontend öffnet ModelMismatchDialog
                 ├─ Revert → PUT mit altem Modell
                 ├─ Reindex → POST /api/search/reindex
                 └─ Später → Warn-Banner persistiert
```

## 7. Error-Handling & Edge-Cases

1. **Embed-Call fehlschlägt** → Log-Warning, `embedding=NULL`, Backfill beim nächsten Start holt nach. Kein Retry im Task.
2. **embed-Capability nicht konfiguriert** → `/api/search/status.configured=false` → Frontend-Banner + Search-Toggle disabled.
3. **Intent-Extract fehlt** → Fallback auf Raw-Query (direkt embedden).
4. **Re-Rank fehlt (HTTP-Fehler oder kaputtes JSON)** → Fallback auf Cosine-Ranking, `reason=null`, Toast „Re-Ranking nicht verfügbar".
5. **Dimension/Modell-Mismatch gespeicherter Embeddings** → `WHERE embedding_model = current_model` filtert heraus. Leere Resultate → `status: "indexing"` mit Progress.
6. **Delete während Embed-Task** → Pre-write Existence-Check, UPDATE auf 0 rows (harmlos).
7. **LLM-Provider Rate-Limit (429)** → Exponential Backoff 1s/2s/4s, max 3 Retries, dann skip.
8. **Paralleler Reindex/Backfill-Trigger** → Modul-Lock, zweiter Call → `409 Conflict`.
9. **Eintrag zu groß für Modell-Token-Limit** → `build_entry_text` kürzt auf ~28000 Zeichen.
10. **Auth/CSRF** → POST-Endpoints nutzen Session + CSRF-Middleware. GET-Status nur Session.

## 8. Testing

### 8.1 Backend (pytest, setup_module/teardown_module-Pattern)

- **`test_embeddings_service.py`**
  - `build_entry_text`: Konkatenation title+content, Kürzung bei Überlänge
  - `pack_vector`/`unpack_vector`: Roundtrip float32, Shape erhalten
  - `cosine_similarity`: vektorisiert, gegen handgerechnete Werte (3 Test-Vektoren)
  - `embed_text`: respx-Mock — Erfolg, 401, 404, 500, ConnectError → korrektes 502-Mapping

- **`test_search_service.py`**
  - `extract_search_intent`: respx-Mock, konversationell → prägnant; Fallback bei Fehler
  - `rerank_results`: gültiges JSON, kaputtes JSON (Fallback), HTTP-Fehler (Fallback)
  - `semantic_search`: End-to-End mit vorab-embedded Test-Entries, Mock-LLM-Calls, Top-K-Sortierung verifiziert

- **`test_search_routes.py`**
  - `POST /api/search`: 200, 401 ohne Session, 403 ohne CSRF, 429 Rate-Limit, 502 bei LLM-Ausfall
  - `GET /api/search/status`: korrekte Counts, `configured` flag
  - `POST /api/search/reindex`: 202 startet, 409 wenn laufend, 403 ohne CSRF
  - Settings-PUT mit Modellwechsel: warning-Payload im Response

- **`test_entries_embedding_invalidation.py`**
  - PATCH Content/Title ändern → `embedding=NULL`, BackgroundTask scheduled (Mock)
  - PATCH nur Tags/Datum → Embedding bleibt
  - DELETE → Row weg (impliziter Cleanup)

- **`test_embedding_jobs.py`**
  - `backfill_missing_embeddings`: seed 5 Entries (3 unembedded, 1 altes Modell, 1 aktuell) → korrekte 4 re-embedded
  - Race: Entry während Embed gelöscht → kein Crash, UPDATE 0 rows
  - 429-Backoff: drei 429-Responses hintereinander → dritter Retry succeeded

### 8.2 Frontend — Vitest

- **`search-store.test.ts`**: Mode-Toggle wechselt Endpoint, Loading-State, Results-Cache
- **`search-ui.test.svelte.ts`**: `SearchToggle` (ARIA, Keyboard), `SearchResultCard` (Score, Reason, Excerpt), `ModelMismatchDialog` (Buttons triggern Events), `ReindexProgress` (Status-Polling)
- **`search-api.test.ts`**: Mock fetch — `searchEntries`, `getSearchStatus`, `reindexEmbeddings` mit CSRF-Header

### 8.3 Frontend — Playwright (`E2E_LIVE`-gated, Skeleton)

- **`semantic-search.spec.ts`**: Login → /entries → Toggle auf Semantik → Query tippen → Results mit Reason sichtbar. Voice-Pfad: Mikro → STT-Mock → Query in Input.

## 9. Offene Punkte für den Implementation-Plan

- Prompt-Formulierungen für `extract_search_intent` und `rerank_results` (auf Deutsch; präzise Formatvorgabe, wenige Shots).
- Genaue slowapi-Limit-Strings (Referenz: `/api/tts`).
- Genaue Alembic-Revision-ID und Filename-Konvention (Referenz: `e3cb482e6e29_add_tts_voice_and_tts_speed_to_settings.py`).
- Frontend-Grafik für Score-Badge — reuse vorhandener Design-Token.

Diese Punkte sind Detailfragen für die Umsetzung, nicht Design-Entscheidungen.

## 10. Geschätzter Aufwand

- Backend: Models + Migration + embeddings/search/jobs Services + 3 Routen + Settings-Anpassung + Tests → **4-5 h**
- Frontend: Store + API-Client + Such-UI mit Toggle + SearchResultList + ModelMismatchDialog + Reindex-Progress + Tests → **3-4 h**
- Integration + manuelles Testen + kleine Fixes → **1 h**

**Gesamt: ~8-10 h** (leicht über Roadmap-Schätzung von 6-8 h wegen Modellwechsel-Dialog und expliziter Fehler-Pfade).
