# Self-Hosting Guide

## 1. DNS

Point your `DOMAIN` at your host's public IP address (an A record with your DNS provider).

For localhost-only development, set `DOMAIN=localhost` — no DNS record is needed.

## 2. Generate Secrets

Run these commands and paste the output into the corresponding `.env` variables:

```bash
openssl rand -hex 32   # → DB_ENCRYPTION_KEY
openssl rand -hex 32   # → SESSION_SECRET
openssl rand -hex 32   # → SECRET_KEY_WRAP
```

Each value must be exactly **64 hex characters** (32 bytes). Do not reuse values across
variables. If these are lost, your encrypted database is unrecoverable — store them
somewhere safe (e.g. a password manager).

## 3. APP_PASSWORD

Set `APP_PASSWORD` in `.env` before the first start. This is the initial login password
for the single-user web interface. It can be changed later via `/settings`.

The config validator rejects obvious weak defaults — the backend refuses to boot if
`APP_PASSWORD` is shorter than 12 characters or in the banned-default list
(`CHANGE_ME`, `changeme`, `password`, `admin`, `testpw`). Generate a real one with:

```bash
openssl rand -base64 18
```

Note: after the first boot the DB-stored password hash is authoritative. Rotating
`APP_PASSWORD` in `.env` does **not** change your login password — only the initial
seed does. To change the actual password, use `/settings` in the UI.

## 4. First Start

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

On first boot the container automatically runs database migrations and seeds default
settings. Check logs with `docker compose -f deploy/docker-compose.yml logs -f app`.

## 5. Login Flow

Open `https://<DOMAIN>/` in your browser and log in with `APP_PASSWORD`.

Optionally enable TOTP (time-based one-time password) two-factor authentication via
`/settings` after logging in.

## 6. Endpoint Configuration

Each of the four AI capabilities (STT, Chat, Embeddings, TTS) has its own:

- **Base URL** — the root of the OpenAI-compatible API (e.g. `https://api.openai.com/v1`)
- **API Key** — passed as `Authorization: Bearer <key>`; use any non-empty string for local servers that ignore it
- **Model** — the model identifier sent in each request

**Minimum setup for all-OpenAI:** just set `OPENAI_API_KEY` in `.env`. Per-capability
key and model fields can stay blank — they fall back to the shared key and to sensible
OpenAI defaults (`whisper-1`, `gpt-4o-mini`, `text-embedding-3-small`, `tts-1`).

See `docs/endpoint-compatibility.md` for the full resolution chain and worked examples
for Ollama / local-only / hybrid setups. All endpoint settings can be changed at runtime
through the Settings UI without restarting the container.

## 7. Data Location

The SQLite database lives at `./data/journal.db` inside the Docker volume and is encrypted
with SQLCipher using `DB_ENCRYPTION_KEY`.

**Back this file up regularly.** Without the correct `DB_ENCRYPTION_KEY` the database
is completely unrecoverable. A simple backup strategy:

```bash
cp ./data/journal.db ./data/journal.db.backup-$(date +%F)
```

## 8. Localhost Dev Note

When `DOMAIN=localhost`, the app sets `Secure=false` on session cookies so that the
application works over plain HTTP (no TLS). This is intentional for local development.

For any deployment reachable from the internet, `DOMAIN` must be a real hostname. The
bundled Caddy reverse proxy will automatically obtain a Let's Encrypt TLS certificate
for that hostname on first start — no manual certificate management is needed.

## 9. Deploying behind a tunnel / upstream proxy

If HTTPS is already terminated by an upstream gateway (Cloudflare Tunnel, Traefik,
nginx-proxy, Authelia, …), Caddy must serve plain HTTP inside the docker network
instead of trying to provision its own certificate. Set in `.env`:

```bash
DOMAIN=yourdomain.example
CADDY_SCHEME=http://
COMPOSE_GATEWAY_NETWORK=<name-of-existing-docker-network>
```

- `CADDY_SCHEME=http://` — Caddy listens on port 80 only, no auto-HTTPS, no redirect loop.
- `COMPOSE_GATEWAY_NETWORK` — an **externally-managed** docker network the upstream gateway
  is already on. Caddy gets attached to it so the gateway can reach `journalai-caddy:80`
  by DNS name, without publishing host ports. Create the network once if it doesn't exist:

  ```bash
  docker network create gateway
  ```

In this mode, the `ports:` block on the caddy service in `docker-compose.yml` stays
commented out — the upstream gateway is the only entry point.

### Cloudflare Tunnel ingress example

Point your tunnel's ingress rule for the hostname at the service DNS name:

```yaml
ingress:
  - hostname: yourdomain.example
    service: http://journalai-caddy:80
```

The `cloudflared` container must be on the same `COMPOSE_GATEWAY_NETWORK`.

## 10. Session Timeouts

- `SESSION_IDLE_MINUTES` (default **20**) — auto-logout after this much inactivity.
- `SESSION_ABSOLUTE_HOURS` (default 12) — hard cap regardless of activity.

The client counts down alongside the server and forces a redirect to `/login` when
the idle window hits zero, so the UI never leaves a stale session visible.
