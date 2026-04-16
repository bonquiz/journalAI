# journalAI — TTS Integration Design

**Status:** Draft
**Datum:** 2026-04-16
**Scope:** Phase 3 (Text-to-Speech überall: Chat-Nachrichten, Einträge, Auto-Play)
**Vorbedingung:** Phase 1 MVP läuft (Tag v0.1.0-mvp + Tag-Verwaltung + Mobile-Polish)

## 1. Ziel und Kontext

TTS-Funktionalität an drei Stellen integrieren:

1. **Chat-Dialog (`/new`)** — jede Assistenten-Nachricht bekommt einen manuellen Play-Button; zusätzlich ein Session-lokales „Auto-Vorlesen"-Toggle, das Antworten nach dem Streaming automatisch vorliest.
2. **Eintrags-Detail (`/entries/[id]`)** — vollwertiger Audio-Player mit Play/Pause, Fortschritt, Zeit-Anzeige, Lautstärke, Tempo-Slider (client-seitig via `audio.playbackRate`).
3. **Global** — Voice und Speed konfigurierbar in `/settings`; Freitext-Voice mit endpoint-sensitivem Tooltip; Fehler via globales Toast-System.

Die App bleibt OpenAI-kompatibel: Der Server ruft `POST /v1/audio/speech` über den konfigurierten `tts_base_url`. Kompatibel mit OpenAI `tts-1`, `openedai-speech`, `kokoro-fastapi`, `orpheus-fastapi`.

## 2. Nicht-Ziele

- Streaming-TTS (Token-by-Token-Synthesis) — Provider-Support ist zu uneinheitlich.
- Server-seitiges Dateicaching — nur Browser-Memory-Cache.
- Voice-Dropdown mit festem Katalog — Freitext bleibt, weil Server variieren.
- Lautstärke global in Settings — nur Browser-Volume.
- Progressive/Streaming-Playback bei sehr langen Einträgen — wir warten auf das komplette MP3.

## 3. Architektur

```
Frontend                          Backend                         TTS-Endpoint
────────                          ───────                         ─────────────
<AudioPlayer>
<PlayMessageButton>
<AutoPlayToggle>
       │
       ▼
lib/tts.ts
┌─────────────────────┐
│  cache: Map<sha256, │    POST /api/tts       routes/tts.py       ┌─────────────┐
│    {blob, url}>     │───────────────────────────────▶│           │ OpenAI/     │
│  hit → return       │                                ▼ chunker   │ Ollama-comp │
│  miss → fetch       │◀─────── audio/mpeg ─────  services/tts.py──▶ Server     │
└─────────────────────┘                                             └─────────────┘
       │
       ▼
URL.createObjectURL(blob)
       │
       ▼
<audio src={blobUrl}>
```

### 3.1 Dateistruktur (neu)

```
backend/app/
├── routes/tts.py           (neu)
├── services/tts.py         (neu)
├── schemas/tts.py          (neu)

backend/alembic/versions/
└── <hash>_add_tts_voice_speed.py  (neu)

frontend/src/lib/
├── tts.ts                  (neu)
├── stores/
│   ├── toast.ts            (neu)
│   └── playback.ts         (neu — koordiniert laufende Audio-Elemente)

frontend/src/lib/components/
├── AudioPlayer.svelte      (neu)
├── PlayMessageButton.svelte (neu)
├── AutoPlayToggle.svelte   (neu)
├── ToastContainer.svelte   (neu)

frontend/src/routes/
├── +layout.svelte          (modify — ToastContainer einbinden)
├── new/+page.svelte        (modify — AutoPlayToggle + Auto-Play-Logik)
├── entries/[id]/+page.svelte (modify — AudioPlayer)
└── settings/+page.svelte   (modify — Voice/Speed-Felder)
```

## 4. Datenmodell

### 4.1 Migration

```sql
ALTER TABLE settings ADD COLUMN tts_voice TEXT;
ALTER TABLE settings ADD COLUMN tts_speed REAL;
```

Beide `NULL` per Default; Service interpretiert `NULL` als „keine Override, Provider-Default verwenden". Wenn kein Wert gesetzt ist, fällt `services/tts.py` auf `"alloy"` / `1.0` zurück.

### 4.2 AppSettings-Erweiterung

```python
tts_voice: Mapped[str | None] = mapped_column(String)
tts_speed: Mapped[float | None] = mapped_column(Float)
```

## 5. Backend

### 5.1 `schemas/tts.py`

```python
from pydantic import BaseModel, Field

class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    voice: str | None = None
    speed: float | None = Field(default=None, ge=0.25, le=4.0)
```

### 5.2 `services/tts.py`

```python
def synthesize(text: str, voice: str | None = None, speed: float | None = None) -> bytes:
    """Generate MP3 bytes for the full text. Chunks at ~3800 chars on sentence
    boundaries to stay under the typical 4096-char provider limit."""
```

- Voice/Speed-Auflösung: `call-param → DB-Settings → hardcoded Default ("alloy" / 1.0)`.
- Chunking: `re.split(r"(?<=[.!?])\s+|\n{2,}", text)`, dann greedy pack in Buckets ≤3800 Zeichen.
- Pro Chunk: `client.audio.speech.create(model=..., voice=..., speed=..., input=chunk, response_format="mp3")`.
- **Speed-Fallback:** bei 400/422 mit „speed" in Fehlermeldung → Retry ohne `speed`-Kwarg (analog zu `chat.finalize`'s JSON-Mode-Fallback).
- MP3-Concat: `b"".join(chunks)` — MP3-Frames sind self-synchronisierend, kein Decoder nötig. Getestet, funktioniert mit OpenAI + openedai-speech.

### 5.3 `routes/tts.py`

```python
router = APIRouter(prefix="/api")

@router.post("/tts")
@limiter.limit("30/minute")
async def tts_endpoint(request: Request, body: TtsRequest) -> StreamingResponse:
    audio = synthesize(body.text, voice=body.voice, speed=body.speed)
    return StreamingResponse(
        iter([audio]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'inline; filename="tts.mp3"'},
    )
```

- Auth + CSRF greifen via bestehende Middleware.
- `text > 20000` → Pydantic validiert → 422.
- TTS-Endpoint unerreichbar → 502 mit JSON-Error (Frontend zeigt Toast).

### 5.4 Settings-Route-Erweiterung

- `SettingsOut` bekommt `tts_voice: str | None`, `tts_speed: float | None`.
- `SettingsPatch` bekommt dieselben Felder (optional).
- `PUT /api/settings` persistiert Werte; `NULL` durch leeren String/None im Request löscht den Override.

### 5.5 Tests (`tests/test_tts.py`)

- `test_synthesize_single_chunk`: kurzer Text → genau 1 respx-Call.
- `test_synthesize_chunks_long_text`: 6000-Zeichen-Text → ≥2 Calls, Output-Länge = Summe.
- `test_synthesize_respects_db_voice`: Settings mit `tts_voice="echo"` → Request-Payload enthält `"voice": "echo"`.
- `test_speed_fallback_on_400`: Mock-Server antwortet 400 mit „speed not supported" → zweiter Call ohne `speed`.
- `test_route_requires_auth`: 401 ohne Session.
- `test_route_too_long_is_422`: Text mit 21000 Zeichen → 422.
- `test_route_rate_limit`: 30 erfolgreiche Calls + 1 mehr → 429.

## 6. Frontend

### 6.1 `lib/tts.ts`

```typescript
const cache = new Map<string, { blob: Blob; url: string }>();

async function hashKey(text: string, voice?: string, speed?: number): Promise<string> {
  const material = `${text}|${voice ?? ""}|${speed ?? ""}`;
  const bytes = new TextEncoder().encode(material);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function synthesize(
  text: string,
  opts: { voice?: string; speed?: number } = {},
): Promise<{ url: string; blob: Blob } | null> {
  const key = await hashKey(text, opts.voice, opts.speed);
  const hit = cache.get(key);
  if (hit) return hit;

  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
      body: JSON.stringify({ text, voice: opts.voice, speed: opts.speed }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const entry = { blob, url };
    cache.set(key, entry);
    return entry;
  } catch (e) {
    toast.error("Vorlesen fehlgeschlagen — TTS-Endpoint prüfen.");
    return null;
  }
}

export function clearCache() {
  for (const { url } of cache.values()) URL.revokeObjectURL(url);
  cache.clear();
}
```

### 6.2 `lib/stores/playback.ts`

Koordiniert das global einzige abspielende `<audio>`, damit neue Play-Aktionen alte stoppen.

```typescript
import { writable } from "svelte/store";

type Current = { id: string; element: HTMLAudioElement } | null;
const current = writable<Current>(null);

export function setCurrent(id: string, element: HTMLAudioElement) {
  current.update((prev) => {
    if (prev && prev.id !== id) prev.element.pause();
    return { id, element };
  });
}

export function stopAll() {
  current.update((prev) => {
    if (prev) prev.element.pause();
    return null;
  });
}

export const currentPlayback = current;
```

### 6.3 `lib/stores/toast.ts`

Siehe Sektion 5 oben — `push`, `dismiss`, Typen `info/success/error`, Errors halten 8 s (andere 5 s).

### 6.4 `components/ToastContainer.svelte`

- Fix-positioniert: Desktop oben rechts, Mobile oben Zentrum (`@media (max-width: 600px)`).
- Svelte-Transitionen `fly` beim Ein-, `fade` beim Ausblenden.
- `role="status"`, `aria-live="polite"` (Errors `aria-live="assertive"`).
- Pro Toast: Farbe (info/success/error), Text, ×-Dismiss-Button.
- In `+layout.svelte` einmalig gerendert.

### 6.5 `components/AutoPlayToggle.svelte`

- `<button role="switch" aria-checked={value}>` mit Info-Icon rechts (nativer `title`-Tooltip).
- Slider-Styling: 42×24 px, grau → `--accent` bei `aria-checked="true"`, Thumb translate 18 px.
- CSS-Transition 150 ms auf `background` + `transform`.
- Label links: „Auto-Vorlesen".
- Reines Frontend-State, nicht persistiert.

### 6.6 `components/PlayMessageButton.svelte`

Kompakter Lautsprecher-Button für Chat-Nachrichten.

States:
- Idle: `🔊` (grau, oder `--muted`)
- Loading: Spinner
- Playing: `⏸` in Primärfarbe
- Paused: `▶`

Props: `text: string`, optional `autoplay: boolean`.

Logik:
1. Klick → falls kein Audio-Blob → `synthesize(text)`; falls null → bleibt idle.
2. Audio-Element erzeugen (lazy), `setCurrent(id, audio)`.
3. `audio.play()` → State wird `playing`.
4. Zweiter Klick: pause oder resume je nach aktuellem State.
5. Wechsel auf andere Nachricht: `stopAll()` → dann neue starten.
6. Cleanup in `onDestroy`: Audio stoppen, ggf. aus Store entfernen.

### 6.7 `components/AudioPlayer.svelte`

Vollwertiger Player für Eintrags-Detail.

Props: `text: string`.

Layout (Desktop ≥600 px):
```
[▶]  [━━━━●────────]  01:23 / 03:45   🔊 [─●──] Tempo [──●──] 1.0×
```

Layout (Mobile <600 px) — zwei Zeilen, Controls wrappen:
```
[▶]  [━━━●──────────]  01:23 / 03:45
🔊 [──●─]      Tempo [──●─] 1.0×
```

Implementierungsdetails:
- Erster Play-Klick: Spinner → `synthesize()` → `<audio>` wird mit `blobUrl` initialisiert → `play()`.
- Fortschrittsbalken als `<input type="range" min=0 max={duration} step=0.1 bind:value={currentTime}>`; `oninput` setzt `audio.currentTime`.
- Speed-Slider als `<input type="range" min=0.5 max=2.0 step=0.1>`; `oninput` setzt `audio.playbackRate`; Default aus `tts_speed` via `/api/settings`-Fetch in `onMount`.
- Volume: `<input type="range" min=0 max=1 step=0.01>`; default 1.0.
- Touch: slider hat erweiterten Hit-Area via `padding: 0.5rem 0` auf dem Input. Thumb visuell 16 px, Track 4 px, mit Webkit- und Moz-Styling.
- Tabular-nums für Zeit-Anzeige.
- Keyboard-Shortcuts: `Space` Play/Pause, `←`/`→` ±5 s Seek.
- Cleanup `onDestroy`: Audio pause, Blob-URL aus Cache bleibt (wird beim Logout revoked).

### 6.8 Integration in `/new`

```svelte
<script>
  let autoPlay = $state(false);
  // ...
  async function send() {
    // ... existing streaming logic ...
    if (autoPlay && assistantMessage) {
      // Trigger TTS on the complete new message
      playMessage(assistantMessage);
    }
  }
</script>

<h1>Neuer Eintrag</h1>
<AutoPlayToggle bind:value={autoPlay} />

{#each $chatDraft as m, i (i)}
  <ChatMessage role={m.role} content={m.content}>
    {#if m.role === "assistant"}
      <PlayMessageButton text={m.content} />
    {/if}
  </ChatMessage>
{/each}
```

`ChatMessage.svelte` bekommt ein `{@render children?.()}` am Ende des `<article>`, damit der Play-Button als Slot einhängbar ist.

### 6.9 Integration in `/entries/[id]`

Direkt unter `<h1>{entry.title}</h1>`:

```svelte
<AudioPlayer text={entry.content} />
```

Falls `/api/tts` 502/500 antwortet → Toast; Player bleibt sichtbar für Retry.

### 6.10 Integration in `/settings`

Neuer Block unter „Endpoints":

```svelte
<fieldset>
  <legend>TTS-Voice & Speed</legend>
  <label>
    Voice
    <input bind:value={form.tts_voice} placeholder={s.tts_voice ?? "alloy"}
           title={voiceTooltip(s.tts_base_url)} />
  </label>
  <label>
    Speed ({form.tts_speed ?? s.tts_speed ?? 1.0}×)
    <input type="range" min="0.5" max="2.0" step="0.05"
           bind:value={form.tts_speed} />
  </label>
</fieldset>
```

`voiceTooltip(url)` gibt je nach Host-String aus `tts_base_url` einen passenden Hinweis zurück:
- enthält `openai.com` → `"z. B. alloy, echo, fable, onyx, nova, shimmer"`
- enthält `kokoro` oder Port 8880 → `"z. B. af_sarah, af_bella, am_adam"`
- enthält `openedai` oder `8000` → `"gemäß voice_to_speaker.yaml des Servers"`
- sonst → `"Laut Dokumentation deines TTS-Servers"`

### 6.11 Logout-Cleanup

In `session.logout()` nach invalidate-Call: `clearCache()` aus `lib/tts.ts` — revokes alle Blob-URLs, leert Map. Keine Audio-Leichen im RAM.

## 7. Fehlerbehandlung

| Szenario | Verhalten |
|---|---|
| TTS-Endpoint 401 | Toast „TTS: Authentifizierung fehlgeschlagen" |
| TTS-Endpoint 404 | Toast „TTS: Modell nicht gefunden" |
| TTS-Endpoint 5xx | Toast „Vorlesen fehlgeschlagen — bitte erneut versuchen" |
| Backend 502 (TTS unreachable) | Toast „TTS-Server nicht erreichbar" |
| Backend 429 (Rate-Limit) | Toast „Zu viele Vorlese-Anfragen — kurz warten" |
| Text >20000 Zeichen | Toast „Eintrag ist zu lang für TTS (max. 20.000 Zeichen)" |

Alle Toasts pausieren die betreffende Komponente in `idle`-State, sodass der User erneut versuchen kann.

## 8. Tests

### 8.1 Backend
Siehe 5.5 — mindestens 7 Tests; Coverage-Ziel ≥80% für `services/tts.py` und `routes/tts.py`.

### 8.2 Frontend (Vitest)
- `tts.test.ts`: Cache-Hit überspringt Fetch, Voice/Speed-Diff erzeugt neuen Key.
- `toast.test.ts`: push/dismiss, Auto-Timeout, Error-Persistenz.
- `playback.test.ts`: setCurrent stoppt vorherigen Audio-Element.
- Komponententests für `AutoPlayToggle` (ARIA-Switch), `PlayMessageButton` (State-Transitions) via Svelte-Testing-Library (neu einzuführen) oder dünne Manual-Tests.

### 8.3 E2E (Playwright)
- Skeleton-Test `tts.spec.ts` (skipped außer `E2E_LIVE=1`): Login → Detail-Seite → Play → erwarte `audio[src]` wird gesetzt.

## 9. Sicherheit

- TTS-Route verlangt Session-Cookie + CSRF-Header (wie alle anderen).
- Text-Payload wird nicht persistiert; der Request lebt nur im Log mit Länge + Status, nicht Inhalt.
- Rate-Limit 30/min verhindert Missbrauch bei kompromittierter Session.
- Response `Content-Disposition: inline` — Browser behandelt MP3 als Stream, nicht als Download.
- Audio-Blob-URLs sind tab-lokal; bei Logout via `clearCache()` revoked.

## 10. Performance

- Chunk-Overhead: bei 6000-Zeichen-Eintrag = 2 sequenzielle TTS-Calls ≈ 4-8 s (OpenAI `tts-1`). Spinner während der Zeit.
- Cache-Hit: instant, kein Netzwerk.
- Audio-Element: `preload="metadata"` statt `auto`, um Initial-Load des Blobs nicht zu duplizieren.
- `audio.playbackRate` ändert sich client-seitig ohne Neu-Request — wichtig für Tempo-Slider.

## 11. Out-of-Scope für diese Phase

- Streaming-TTS (Token-by-Token).
- Server-Dateicache (Option C aus der Brainstorming-Phase).
- Voice-Dropdown mit Provider-Auto-Detect.
- Hintergrund-Prerender bei Eintrag-Speichern.
- TTS für Transkripte (`raw_transcript`).
- Download-Button für MP3-Datei (Browser kann via Rechtsklick → Audio speichern).

## 12. Offene Punkte

- **MP3-Concat-Robustheit:** `b"".join()` klappt bei CBR-MP3 der genannten Provider. Falls ein Provider VBR mit Xing-Header ausgibt, kann es zu Dauer-Anzeige-Problemen kommen. Fallback: pydub einbinden — aber das fügt eine 25-MB-Dependency hinzu. Erst fixen wenn es Probleme gibt.
- **Toast-Stil:** Svelte-Transitions brauchen keinen extra Import, aber die Farben definieren wir während Implementation anhand des bestehenden Theme.
- **Touch-Gesten Fortschrittsbalken:** Native `<input type="range">` funktioniert auf iOS/Android out-of-the-box; falls das Handling bei schnellen Swipes ruckelt, können wir auf custom Progress-Bar mit `touchmove` wechseln.
