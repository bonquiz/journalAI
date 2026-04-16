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

See `docs/endpoint-compatibility.md` for worked examples. All endpoint settings can be
changed at runtime through the Settings UI without restarting the container.

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
