# Claude Code — Hinweise für dieses Repo

Sprache für alle Antworten und Commits: **Deutsch**. Bei technischen Begriffen (Paketnamen, Identifier, Pfade) im Original belassen.

## Wo was liegt

- **Fortschritt / Stand / nächste Ziele:** `~/.claude/projects/-home-julian-Projekte-journalAI/memory/roadmap.md` — Single-Source-of-Truth. Bei Session-Start lesen, nach jedem Commit updaten (Auto-Memory-Regel steht dort).
- **Specs & Pläne:** `docs/superpowers/specs/` und `docs/superpowers/plans/`
- **Bedien-Doku:** `README.md` (EN), `README.de.md`, `docs/self-hosting.md`, `docs/self-hosting/*.md`, `docs/endpoint-compatibility.md`

## Stack in zwei Zeilen

FastAPI + SQLAlchemy 2 + SQLCipher + Alembic. SvelteKit 2 + Svelte 5 runes (SPA, `ssr=false`). Docker-Compose: `caddy` + `backend` + `frontend`. OpenAI-kompatible Endpoints für STT / Chat / Embed / TTS mit ENV- und DB-Overrides.

## Kommandos

- Backend-Tests: `cd backend && .venv/bin/pytest -q` (braucht einmalig `apt install libsqlcipher-dev sqlcipher pkg-config build-essential`)
- Frontend-Tests: `cd frontend && npm test -- --run`
- Frontend-Typcheck: `cd frontend && npm run check`
- Frontend-Build: `cd frontend && npm run build`
- Full restart lokal: `docker compose -f deploy/docker-compose.yml down && docker compose -f deploy/docker-compose.yml up -d --build`

## Deploy auf qrackz (QNAP Container Station)

Dieses Repo ist auch live als `diary.bonquiz.site` hinter einem Cloudflare Tunnel deployed. SSH-Zugang siehe `~/.claude/projects/.../memory/ssh_qrackz.md`.

- Code liegt auf qrackz unter `/share/CACHEDEV1_DATA/Container/journalAI/` — **ohne `.git`**, wird per `rsync` synchronisiert.
- `git` ist auf dem NAS nicht installiert, `python3` auch nicht — für Remote-Scripting nur POSIX-Shell + `sed`/`awk`.
- Vor `docker` per SSH: `export PATH=$PATH:/share/CACHEDEV1_DATA/.qpkg/container-station/bin`
- Typischer Flow: Änderung committen + pushen, dann `rsync` der geänderten Dateien → `docker compose up -d --build <service>` auf qrackz.
- Prod-`.env` dort:
  - `DOMAIN=diary.bonquiz.site`
  - `CADDY_SCHEME=http://` (TLS terminiert der CF-Tunnel)
  - `COMPOSE_GATEWAY_NETWORK=n8n-stack_web` (externes Docker-Netzwerk, auf dem auch der `cloudflared`-Container sitzt)
  - `APP_PASSWORD` ist ein 32-Hex-Placeholder — das **echte** Login-Passwort liegt als Hash in der DB und wird vom ENV nur beim allerersten Bootstrap gesetzt.

## Gotchas, die schon Zeit gekostet haben

- **Cache-Poisoning durch 3xx-Antworten:** Caddy setzt `Cache-Control: no-store` auf `/api/*`, weil ein früher falsch konfigurierter 308-Redirect im Browser-Cache landete und alle API-Calls tot gemacht hat. Nie entfernen. Bei „rätselhaftem Auth-Verhalten, Server-Logs zeigen nichts": erst **DevTools → Network-Tab** (inkl. „Disable cache"), dann Server-Logs.
- **Cloudflare Access vor der API:** Expired-Token-Fälle antworten mit **302** zu `cloudflareaccess.com` (nicht 401). `frontend/src/lib/stores/session.ts` fängt das mit `redirect: "manual"` + `isGatewayChallenge()` ab → `window.location.reload()`.
- **SQLCipher-Tests teilen sich eine DB:** Jede Test-Datei braucht `engine.dispose()` + `Base.metadata.create_all(engine)` im `setup_module` und Zeilen-Delete im `teardown_module`.
- **`pysqlcipher3` braucht SQLAlchemy-Dialekt `sqlite+pysqlcipher`**: `sqlcipher3-wheels` funktioniert damit NICHT.
- **SSE-Tokens sind JSON-encodiert** — sonst brechen Newlines das Framing.
- **`@testing-library/svelte` v5** braucht `resolve.conditions: ["browser"]` in `vitest.config.ts` + `cleanup()` in `afterEach`.
- **Hetzner Cloud hat keine GPU-Instanzen** (Stand April 2026). `./scripts/hetzner/bootstrap.sh --tier recommended` bricht absichtlich ab. Für GPU siehe RunPod-Kommentar in der Roadmap.
- **Frontend läuft als non-root**: `nginxinc/nginx-unprivileged` hört auf `:8080`, nicht `:80`. Caddy proxied entsprechend auf `frontend:8080`.
- **Backend ist `read_only: true`**: `PYTHONDONTWRITEBYTECODE=1` gesetzt, damit kein `__pycache__` geschrieben werden muss. SQLCipher `mlock()` schlägt fehl (warning in Logs) — das ist das Fehlen von `CAP_IPC_LOCK`, nicht schlimm.

## Arbeitsweise in diesem Repo

- Keine Feature-Branches — alles auf `main` mit sauberen, atomaren Commits. Für größere, risikoreiche Themen erst Plan in `docs/superpowers/plans/` schreiben.
- `superpowers:subagent-driven-development` hat sich bewährt: Implementer → Spec-Review → Code-Quality-Review pro Task. Besonders sinnvoll bei >3 Subtasks.
- Bei Security/Architektur-Entscheidungen einen **Codex-Review** vor Merge einholen (`codex-dialog` Skill).
- Nach jedem Commit: `memory/roadmap.md` updaten.
