# Lokaler LLM-Stack (Design)

**Datum:** 2026-04-19
**Version:** `v0.5.0-local-llm`
**Branch:** `main` (keine Feature-Branches, wie im Projekt üblich)

## Ziele

journalAI soll ohne Cloud-LLM-Provider betreibbar sein — vollständig lokal, privacy-first. Alle vier LLM-Capabilities (STT, Chat, Embeddings, TTS) laufen in Docker-Containern neben Backend und Frontend. Gleichzeitig bleibt der bestehende OpenAI-Fallback-Weg unangetastet: ein `OPENAI_API_KEY` allein reicht weiterhin für einen sofort lauffähigen Stack.

Sekundärziel: Self-Hoster ohne geeignete lokale Hardware bekommen einen dokumentierten, skriptgestützten Pfad, um den Stack temporär auf Hetzner Cloud zu betreiben und so vor dem Dauerbetrieb zu evaluieren.

## Scope

**Drin:**
1. **Voller lokaler Stack** — Ollama (Chat + Embed), speaches (STT, faster-whisper-Backend), Kokoro-FastAPI (TTS), alle OpenAI-kompatibel.
2. **Zwei Tiers:** Minimal (CPU-only) und Recommended (NVIDIA-GPU).
3. **Compose-Overlays** — `docker-compose.local-llm.yml` + `docker-compose.local-llm.gpu.yml`.
4. **Backend-Resolution-Chain** — neue ENV-Zweig pro Capability (`CHAT_BASE_URL`, `EMBED_BASE_URL`, `STT_BASE_URL`, `TTS_BASE_URL`), greift wenn DB-Setting leer.
5. **Hetzner-Bootstrap** — Bash-Skripte `scripts/hetzner/bootstrap.sh` + `teardown.sh` für On-Demand-Tests via HCloud CLI.
6. **Benchmark-Skript** `scripts/benchmark.sh` — misst Tokens/s, RTF, Entries/s gegen eine laufende Instanz. Ergebnisse als Markdown-Reports committbar.
7. **Dokumentation** — `docs/self-hosting/local-llm.md` (Stack-Betrieb) und `docs/self-hosting/hetzner.md` (B-Pfad inkl. Tailscale-Hardening).

**Raus (YAGNI):**
- U3-Volume-Trennung für Backend-Daten (bleibt eigenes Upgrade).
- Alternative lokale STT-Engines (Parakeet etc. — das ist U6).
- Auto-GPU-Detect im Compose (zwei explizite Overlay-Dateien sind ehrlicher).
- Streaming von Model-Downloads in den Init-Container oder Progress-UI.
- Multi-Tenant/Concurrency-Optimierungen für Ollama (Single-User-App).
- Web-UI zum Modellwechsel (weiterhin via ENV oder `/settings`).

---

## 1. Architektur

### Services

Alle Services laufen im bestehenden Compose-Netz `journalai_net`, erreichbar über Docker-DNS via Servicenamen. Nur Caddy (bestehend) hat Port 443 öffentlich gebunden.

| Service | Image | Interner Port | Volume |
|---|---|---|---|
| `ollama` | `ollama/ollama:latest` | `11434` | `ollama_models:/root/.ollama` |
| `speaches` | `ghcr.io/speaches-ai/speaches:latest-cpu` bzw. `-cuda` | `8000` | `speaches_models:/home/ubuntu/.cache/huggingface` |
| `kokoro` | `ghcr.io/remsky/kokoro-fastapi-cpu:latest` bzw. `-gpu` | `8880` | `kokoro_models:/app/models` |
| `ollama-init` | `ollama/ollama:latest` (one-shot) | — | — |

Der `ollama-init`-Container läuft einmalig beim `up` und pullt die aktuell konfigurierten Chat- und Embed-Modelle (`docker exec ollama ollama pull $CHAT_MODEL` Pattern via `entrypoint`-Override). `restart: no`. Idempotent: existierende Modelle werden von Ollama übersprungen.

### Default-Modelle pro Tier

| Capability | Minimal (CPU) | Recommended (GPU) |
|---|---|---|
| Chat | `qwen2.5:3b-instruct-q4_K_M` | `qwen2.5:7b-instruct-q4_K_M` |
| Embed | `all-minilm` (384-dim) | `bge-m3` (1024-dim) |
| STT | `Systran/faster-whisper-base` | `Systran/faster-whisper-large-v3` |
| TTS | `kokoro` | `kokoro` |

Beide Tiers werden in `.env.local-llm.example` als kommentierte Blöcke gezeigt; User setzt den gewünschten Block aktiv.

### Embedding-Dimensions-Wechsel

Ein Wechsel zwischen `all-minilm` (384) und `bge-m3` (1024) verändert die Embedding-Dimension. Die bestehende `embedding_model_mismatch`-Warnung aus der semantischen Suche greift; `U1`-Schema (`entry_embeddings.dim`) erlaubt den Parallelbetrieb, der ModelMismatchDialog bietet Reindex/Revert. Kein zusätzlicher Code nötig.

---

## 2. Compose-Dateien

### Neue Dateien

```
deploy/
  docker-compose.local-llm.yml          # Base: ollama, speaches, kokoro, ollama-init
  docker-compose.local-llm.gpu.yml      # Overlay: deploy.resources NVIDIA-Reservations
  .env.local-llm.example                # Muster-ENV mit beiden Tier-Blöcken
```

### Base (CPU-tauglich)

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    volumes:
      - ollama_models:/root/.ollama
    networks: [journalai_net]
    healthcheck:
      test: ["CMD", "ollama", "list"]
      interval: 10s
      timeout: 5s
      retries: 5

  ollama-init:
    image: ollama/ollama:latest
    depends_on:
      ollama:
        condition: service_healthy
    restart: "no"
    entrypoint: ["/bin/sh", "-c"]
    command: >
      "OLLAMA_HOST=http://ollama:11434 ollama pull ${CHAT_MODEL} &&
       OLLAMA_HOST=http://ollama:11434 ollama pull ${EMBED_MODEL}"
    networks: [journalai_net]

  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cpu
    restart: unless-stopped
    volumes:
      - speaches_models:/home/ubuntu/.cache/huggingface
    networks: [journalai_net]
    environment:
      - WHISPER__MODEL=${STT_MODEL}

  kokoro:
    image: ghcr.io/remsky/kokoro-fastapi-cpu:latest
    restart: unless-stopped
    volumes:
      - kokoro_models:/app/models
    networks: [journalai_net]

  backend:
    env_file:
      - .env.local-llm

volumes:
  ollama_models:
  speaches_models:
  kokoro_models:
```

Das `backend`-Fragment fügt nur das zusätzliche `env_file` hinzu; alle anderen bestehenden Backend-Einstellungen kommen aus `docker-compose.yml`.

### GPU-Overlay

```yaml
services:
  ollama:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
  speaches:
    image: ghcr.io/speaches-ai/speaches:latest-cuda
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
  kokoro:
    image: ghcr.io/remsky/kokoro-fastapi-gpu:latest
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### Startkommandos

**Minimal (CPU):**
```
docker compose -f docker-compose.yml -f docker-compose.local-llm.yml \
  --env-file .env --env-file .env.local-llm up -d
```

**Recommended (GPU):**
```
docker compose -f docker-compose.yml -f docker-compose.local-llm.yml \
  -f docker-compose.local-llm.gpu.yml \
  --env-file .env --env-file .env.local-llm up -d
```

`nvidia-container-toolkit` muss auf dem Host installiert sein; bootstrap.sh installiert das automatisch im Recommended-Tier.

---

## 3. Backend-Änderungen

### Resolution-Chain-Erweiterung

Bestehende Logik in `backend/app/services/llm_client.py`:

```
resolved_model(cap): DB → ENV → OpenAI-Default (falls base_url=api.openai.com)
```

Neu (symmetrisch für `base_url` und `api_key`):

```
resolved_base_url(cap):  DB → ENV ({CAP}_BASE_URL) → "https://api.openai.com/v1"
resolved_api_key(cap):   DB → ENV ({CAP}_API_KEY)  → ENV (OPENAI_API_KEY)
resolved_model(cap):     DB → ENV ({CAP}_MODEL)    → OpenAI-Default (unverändert)
```

`get_client(cap)` nutzt intern die drei Resolver.

### Neue ENV-Variablen

In `.env.local-llm.example`:

```
# Chat
CHAT_BASE_URL=http://ollama:11434/v1
CHAT_API_KEY=ollama
CHAT_MODEL=qwen2.5:7b-instruct-q4_K_M

# Embeddings
EMBED_BASE_URL=http://ollama:11434/v1
EMBED_API_KEY=ollama
EMBED_MODEL=bge-m3

# Speech-to-Text
STT_BASE_URL=http://speaches:8000/v1
STT_API_KEY=speaches
STT_MODEL=Systran/faster-whisper-large-v3

# Text-to-Speech
TTS_BASE_URL=http://kokoro:8880/v1
TTS_API_KEY=kokoro
TTS_MODEL=kokoro
TTS_VOICE=af_sky
```

`CHAT_API_KEY=ollama` ist ein Pseudo-Wert — Ollama akzeptiert jeden nicht-leeren Bearer-Token, aber die OpenAI-SDK im Backend erwartet einen String.

### API-Response-Erweiterung

`GET /api/settings` liefert bislang nur DB-Werte. Neu: das Response-Modell enthält zusätzlich `resolved_base_url`, `resolved_model` pro Capability (read-only), sodass das Frontend erkennen kann, ob eine Capability gerade aus ENV oder DB kommt.

```json
{
  "chat": {
    "base_url": "",              // DB-Wert (leer = ENV/Default greift)
    "model": "",
    "resolved_base_url": "http://ollama:11434/v1",
    "resolved_model": "qwen2.5:7b-instruct-q4_K_M"
  },
  ...
}
```

Frontend rendert den resolved-Wert als graue Hinweiszeile („aus ENV: …") unter dem leeren Input-Feld. Kein State-Management-Change, nur Darstellung.

### Tests

- Unit-Tests für `resolved_base_url`, `resolved_api_key` (je 3 Fälle: DB-Hit, ENV-Hit, Fallback).
- 1 Integrations-Test: ohne DB-Eintrag und mit `CHAT_BASE_URL`-ENV wird `httpx`-Client gegen die ENV-URL instanziiert (Monkey-Patch `httpx.AsyncClient`).
- Bestehende 155 Backend-Tests bleiben grün.

---

## 4. Hetzner-Bootstrap (B-Pfad)

### Dateien

```
scripts/hetzner/
  bootstrap.sh            # Server erstellen + Stack starten
  teardown.sh             # Server + Firewall löschen
.env.hetzner.example      # Vorlage (gitignored: .env.hetzner)
docs/self-hosting/
  local-llm.md            # Stack-Betrieb (lokal + Hetzner gleichermaßen)
  hetzner.md              # HCloud-spezifischer Pfad + Tailscale-Abschnitt
```

### `.env.hetzner.example`

```
# HCloud-API-Token (https://console.hetzner.cloud/ → Security → API Tokens)
HCLOUD_TOKEN=

# Label eines in HCloud hinterlegten SSH-Keys
HCLOUD_SSH_KEY=

# Location (nbg1, fsn1, hel1, ash, hil)
HCLOUD_LOCATION=nbg1

# Server-Name (default journalai-test)
HCLOUD_SERVER_NAME=journalai-test

# Domain (optional; default sslip.io-Fallback)
DOMAIN=
```

### `bootstrap.sh` — Ablauf

1. `set -euo pipefail`. ENV aus `.env.hetzner` laden, falls vorhanden und ENV-Vars noch nicht gesetzt.
2. Preflight-Check: `hcloud` im PATH, `HCLOUD_TOKEN` gesetzt, SSH-Key-Label existiert, lokale `.env` + `.env.local-llm` vorhanden (werden später per `scp` übertragen).
3. Args parsen: `--tier minimal|recommended` (default `minimal`), `--yes` (skip confirmation).
4. Firewall `journalai-test-fw` anlegen/finden. Regeln: SSH (22) nur von `$(curl -s ifconfig.me)`, TCP 443 von `0.0.0.0/0`, TCP 80 von `0.0.0.0/0` (Let's-Encrypt HTTP-01).
5. Server anlegen: Typ `cpx41` (minimal) / `gex44` (recommended), Image `ubuntu-24.04`, mit Cloud-init (siehe unten), Firewall attached.
6. Auf SSH warten (`ssh -o ConnectTimeout=5` in Retry-Loop).
7. IP ausgeben und Default-Domain berechnen: `${DOMAIN:-${IP}.sslip.io}`.
8. `scp .env .env.local-llm user@ip:journalAI/deploy/` (DOMAIN wird via `sed` auf IP.sslip.io gesetzt, falls leer).
9. Via SSH: `cd journalAI/deploy && docker compose -f … up -d` mit passenden Overlays je Tier.
10. Warte auf Healthcheck (`curl -sf https://…/api/health` mit Backoff, max. 5 min — Modell-Downloads beim ersten Lauf können dauern).
11. Ausgabe: URL, SSH-Kommando, Teardown-Hinweis, Kosten pro Stunde.

### Cloud-init-Payload (inline im Skript)

```yaml
#cloud-config
package_update: true
package_upgrade: false
packages:
  - ca-certificates
  - curl
  - git
  - jq
runcmd:
  - curl -fsSL https://get.docker.com | sh
  - usermod -aG docker ubuntu
  - |
    if [ "$TIER" = "recommended" ]; then
      curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
      curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        > /etc/apt/sources.list.d/nvidia-container-toolkit.list
      apt-get update && apt-get install -y nvidia-container-toolkit
      nvidia-ctk runtime configure --runtime=docker
      systemctl restart docker
    fi
```

**Code-Transfer:** Das Repo ist derzeit lokal-only (kein Remote konfiguriert). `bootstrap.sh` überträgt den lokalen Working-Tree via `rsync -az --exclude='.git' --exclude='node_modules' --exclude='backend/.venv' --exclude='deploy/data' <repo-root>/ user@ip:journalAI/`. Das funktioniert ohne Public Repo und erlaubt Tests gegen uncommitted-Changes. Wenn später ein Public Remote existiert, kann das Skript alternativ `git clone` via `HCLOUD_REPO_URL`-ENV nutzen (Fallback-Branch im Skript, Default = rsync).

### `teardown.sh`

`hcloud server delete "$HCLOUD_SERVER_NAME" && hcloud firewall delete journalai-test-fw`. Bestätigungs-Prompt, außer mit `--yes`. Fehler bei nicht-existenten Ressourcen werden ignoriert (idempotent).

### Tailscale-Härtung (nur Doku, kein Skript-Zweig)

`docs/self-hosting/hetzner.md` enthält einen Abschnitt „Maximal abgeschottet":
1. Tailscale auf Client + Server installieren (`curl -fsSL https://tailscale.com/install.sh | sh`).
2. `sudo tailscale up` auf beiden Seiten.
3. HCloud-Firewall-Regel für 443 entfernen oder auf Tailscale-Netz (100.64.0.0/10) beschränken — beide Wege dokumentiert.
4. Caddy-Config auf Tailscale-Hostname umstellen (optional, via ENV).

Kein Skript-Support, weil Tailscale-Auth-Keys einen eigenen Login-Flow brauchen und wir sie nicht in `.env` verwalten wollen.

---

## 5. Benchmarks & Tests

### `scripts/benchmark.sh`

Args: `--url https://host/` (Pflicht), `--tier minimal|recommended` (fürs Report-Frontmatter), `--label custom-name` (optional).

Ablauf:

1. Login gegen `/api/auth/login` (Credentials aus `.env.benchmark` — gitignored).
2. **Chat-Benchmark** — POST an `/api/chat` mit Fixed-Prompt, SSE konsumieren, Tokens zählen, Wall-Time messen → `chat_tokens_per_second`.
3. **STT-Benchmark** — Upload `tests/fixtures/benchmark-60s.webm` (1-minütiges Test-Audio, einmalig ins Repo committed), Wall-Time messen → `stt_rtf = duration_s / 60`.
4. **Embed-Benchmark** — vorheriges Setup: via API 100 Test-Entries erzeugen. POST `/api/search/reindex`, polling `/api/search/status` bis `done`. → `embed_entries_per_second`.
5. **TTS-Benchmark** — POST `/api/tts` mit 300-Zeichen-Text, Audiolänge aus Response-Headers oder `ffprobe`, Wall-Time messen → `tts_rtf`.
6. Teardown: Test-Entries löschen.
7. Output-Tabelle auf stdout + Report schreiben nach `docs/benchmarks/YYYY-MM-DD-<tier>-<hostname>.md` mit Frontmatter (`tier`, `hostname`, `cpu`, `ram`, `gpu`, `models`, Ergebnisse).

### Test-Fixtures

- `tests/fixtures/benchmark-60s.webm` — 60 Sekunden deutsche Sprachaufnahme, unter CC0 lizensiert. Wird einmal manuell erstellt und committed (≤2 MB).

### CI

- Neuer Job `local-llm-compose-validate.yml`: führt `docker compose config` auf beide Overlays aus. Fängt YAML-Syntaxfehler. Kein Modell-Download, kein Container-Start.
- Bestehende backend-test- und frontend-test-Workflows bleiben unverändert.

### E2E

Bestehende Playwright-Suite akzeptiert bereits `PLAYWRIGHT_BASE_URL` via ENV. Für den Hetzner-Durchlauf setzt der User `PLAYWRIGHT_BASE_URL=https://<ip>.sslip.io`; die Suite läuft unverändert und validiert den vollen Stack.

---

## 6. Akzeptanzkriterien

- **Compose-Start:** `docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up -d` bringt vier Services healthy hoch (Minimal-Tier, CPU-only) und journalAI erreichbar auf 443.
- **Backend-Resolution:** Bei leeren DB-Settings und gesetzten `CHAT_BASE_URL`-ENV schlagen Chat-Requests tatsächlich gegen Ollama auf. Unit-Tests decken alle drei Resolver ab.
- **Fallback-Modus:** Ohne local-llm-Overlay und mit `OPENAI_API_KEY`-ENV funktioniert alles wie bisher. Keine Regression in den bestehenden 155 Backend-Tests.
- **Hetzner-Bootstrap:** `bootstrap.sh --tier minimal` erzeugt einen funktionierenden Server in unter 10 min (exkl. Modell-Downloads) und gibt eine erreichbare URL aus. `teardown.sh` räumt vollständig auf.
- **Benchmark:** `benchmark.sh` produziert einen committbaren Markdown-Report für beide Tiers mit plausiblen Werten.
- **Dokumentation:** `docs/self-hosting/local-llm.md` erklärt den lokalen Betrieb in ≤5 Schritten; `docs/self-hosting/hetzner.md` deckt Bootstrap, Kosten und Tailscale-Abschnitt ab. README verlinkt beide und enthält die Benchmark-Zusammenfassung.

## 7. Risiken & offene Fragen

- **Kokoro-Bildgrößen** — Die GPU-Variante ist mehrere GB groß. Erster Start auf Hetzner kann lange dauern; der Healthcheck-Wait in `bootstrap.sh` muss großzügig dimensioniert sein (5-10 min).
- **speaches-Kompatibilität** — Die OpenAI-STT-API-Surface wird von speaches abgedeckt, aber `language`-Autodetect und Response-Schema müssen gegen unseren bestehenden STT-Client validiert werden. Wenn Probleme: Fallback auf `faster-whisper-server` (gleiche Klasse) oder expliziter `language=de`-Param.
- **Ollama Embed-Response-Format** — Ollama liefert Embeddings im OpenAI-Format seit v0.1.47. Sollte der Cluster eine ältere Version ziehen, greift unser `embedding_jobs._embed_one_with_backoff` mit 502-Mapping. Lösung: Image-Tag pinnen statt `latest`.
- **HCloud-Firewall vs. IP-Wechsel** — `bootstrap.sh` öffnet SSH nur für die aktuelle öffentliche IP des Ausführenden. Bei Wechsel (neues WLAN, VPN an/aus) muss die Firewall manuell aktualisiert werden (`hcloud firewall replace-rules`). Wird im Runbook erwähnt.
- **Minimal-Tier-Ehrlichkeit** — Wir versprechen realistische Tokens/s. Erste Hetzner-Messung dient als Referenz; wenn die Werte unter ~3 tok/s fallen, markieren wir Minimal-Tier als „proof of concept, nicht für Tagesbetrieb".
