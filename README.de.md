# journalAI

**Selbst gehostetes, datenschutz-freundliches Sprach- und Text-Tagebuch mit LLM-Unterstützung.**
Diktiere oder tippe Einträge, lasse sie von einem LLM strukturieren, suche in natürlicher Sprache — und behalte alle Daten auf deinem eigenen Server. Funktioniert mit jeder OpenAI-kompatiblen API (Cloud oder vollständig lokal).

🇬🇧 **[English version → README.md](README.md)**

---

## Features

- 🎙️ **Sprache oder Text** — Memo diktieren oder direkt tippen
- 💬 **Chat-gestütztes Finalisieren** — Entwurf in kurzem Dialog verfeinern, bevor gespeichert wird
- 🏷️ **Tags** — Umbenennen, Zusammenführen, Löschen unter `/tags`
- 🔍 **Semantische Suche** — natürlichsprachig fragen (*„hab ich mal über einen Regenbogen-Traum geschrieben?"*); ein LLM re-rankt die Treffer mit einer kurzen Begründung
- 🔊 **Vorlesen (TTS)** — jeden Eintrag oder jede Chat-Antwort abspielen
- 🔐 **Verschlüsselt im Ruhezustand** — komplette SQLCipher-Verschlüsselung der Datenbank
- 🏠 **Selbst-gehostet** — Docker Compose + automatisches HTTPS via Caddy

## Zwei Deploy-Pfade — wähle einen

### 🚀 Pfad A: „Funktioniert einfach" (nur OpenAI, ≈ 5 Minuten)

Du brauchst: einen OpenAI-API-Key, eine Maschine mit Docker und eine Domain (oder localhost).

```bash
git clone https://github.com/bonquiz/journalAI.git
cd journalAI
./scripts/init-env.sh        # stellt 3 Fragen, generiert alle Secrets
docker compose -f deploy/docker-compose.yml up -d
```

`init-env.sh` fragt ab:
1. Domain (oder `localhost`)
2. App-Passwort
3. Dein OpenAI-API-Key

Die drei 64-hex-Secrets (`DB_ENCRYPTION_KEY`, `SESSION_SECRET`, `SECRET_KEY_WRAP`) werden automatisch generiert — die musst du nie selbst anfassen.

Öffne `https://<deine-domain>` und melde dich mit deinem App-Passwort an. Fertig.

### 🏠 Pfad B: Vollständig lokal, ohne Cloud (≈ 30 Minuten)

Du brauchst: eine Maschine mit Apple Silicon / Consumer-NVIDIA-GPU (≥ 8 GB VRAM empfohlen) ODER eine starke CPU (≥ 8 Kerne) — plus ~50 GB Speicher für die Modelle.

```bash
git clone https://github.com/bonquiz/journalAI.git
cd journalAI
./scripts/init-env.sh        # wähle Option 3 bei der LLM-Auswahl

cp deploy/.env.local-llm.example deploy/.env.local-llm
# In .env.local-llm: den Minimal- (CPU) oder Recommended- (GPU) Block einkommentieren

# CPU:
docker compose \
  -f deploy/docker-compose.yml \
  -f deploy/docker-compose.local-llm.yml \
  --env-file deploy/.env --env-file deploy/.env.local-llm \
  up -d

# GPU: zusätzlich -f deploy/docker-compose.local-llm.gpu.yml (setzt nvidia-container-toolkit voraus)
```

Komplette Anleitung lokaler Stack: **[`docs/self-hosting/local-llm.de.md`](docs/self-hosting/local-llm.de.md)**

Keine eigene Hardware? Ein temporärer Hetzner-Cloud-Server reicht für die Evaluation: **[`docs/self-hosting/hetzner.de.md`](docs/self-hosting/hetzner.de.md)** (≈ 0,04 €/h).

### 🔀 Gemischter Betrieb

Jede Capability (Chat, Embed, STT, TTS) hat eigene Base-URL / API-Key / Modell. Du kannst z. B. Chat auf lokalem Ollama laufen lassen und OpenAI für Whisper-STT nutzen. Konfiguration nach dem Login unter `/settings` oder in `deploy/.env`.

## Mindestanforderungen

- **Pfad A (Cloud):** Beliebiger Linux-Server, 1 vCPU, 1 GB RAM, Docker + Docker Compose v2.
- **Pfad B (lokal):** 8+ CPU-Kerne oder GPU ≥ 8 GB VRAM, 16 GB RAM, 50 GB Speicher. Details in [`docs/hardware-profiles.md`](docs/hardware-profiles.md).

## Performance — ehrliche Zahlen (gemessen 2026-04-19)

| Tier | Hardware | Chat | STT (RTF) | Embed | TTS (RTF) | ~ Kosten/h |
|---|---|---|---|---|---|---|
| Minimal | Hetzner cpx42 (CPU) + qwen2.5:**3b** | 94 chars/s (~15 tok/s) | 0,03 | 3,5/s (nomic) | 0,3 | 0,04 € |
| Recommended | RunPod RTX 4090 + qwen2.5:**7b** | **639 chars/s / 158 tok/s** | — | — | — | 0,34 $ |

⚠️ **Ehrlichkeitshinweis:** Das Minimal-Tier funktioniert, aber qwen2.5:3b hat spürbare Grammatik- und Wortfindungsfehler. Für den täglichen Gebrauch empfehlen wir das GPU-Tier mit qwen2.5:14b oder größer (Hetzner Cloud bietet derzeit keine GPU-Instanzen — siehe den Hetzner-Guide für Alternativen wie RunPod, Lambda, Paperspace).

Detaillierte Reports: [`docs/benchmarks/`](docs/benchmarks/).

## Dokumentation

- **[`docs/self-hosting.md`](docs/self-hosting.md)** — Produktion-Deploy (DNS, Backups, Updates)
- **[`docs/self-hosting/local-llm.de.md`](docs/self-hosting/local-llm.de.md)** — kompletter lokaler Stack (🇩🇪) / [EN](docs/self-hosting/local-llm.md)
- **[`docs/self-hosting/hetzner.de.md`](docs/self-hosting/hetzner.de.md)** — Hetzner-Bootstrap + Tailscale-Härtung (🇩🇪) / [EN](docs/self-hosting/hetzner.md)
- **[`docs/endpoint-compatibility.md`](docs/endpoint-compatibility.md)** — welche Provider/Server funktionieren
- **[`docs/hardware-profiles.md`](docs/hardware-profiles.md)** — Hardware-Empfehlungen für lokale Setups

## E2E-Tests

Playwright-Specs unter `frontend/tests/e2e/` sind per `E2E_LIVE=1` gegated, weil sie echte LLM-Requests erzeugen (Kosten + Latenz).

```bash
cd frontend
E2E_LIVE=1 \
  OPENAI_API_KEY=<dein-openai-key> \
  OPENAI_BASE_URL=https://api.openai.com/v1 \
  npx playwright test
```

## Datenschutz

Nichts aus deinem Tagebuch, Audio oder Secrets landet jemals in diesem Repository. Deine Daten liegen im Docker-Volume `./data/` (SQLCipher-verschlüsselt). Audio-Dateien werden unmittelbar nach der Transkription verworfen.

## Lizenz

MIT — siehe [`LICENSE`](LICENSE).

## Mitmachen

Issues und Pull Requests willkommen unter https://github.com/bonquiz/journalAI.
