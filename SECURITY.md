# Security Policy

journalAI is a self-hosted application that handles private journal entries
and encryption keys. I take reports seriously.

## Supported Versions

Only the latest tagged release on `main` is supported. Please verify the
issue still reproduces against `main` before reporting.

## Reporting a Vulnerability

**Please do not open public GitHub issues for security problems.**

Email: `security+journalai@bonquiz.site`

Please include:

- A description of the issue and its impact (what an attacker can do).
- Reproduction steps — minimal config, exact commands, expected vs. actual
  behavior. A working PoC against a fresh deployment is ideal.
- Affected commit/tag.
- Your preferred contact and whether you want credit in the advisory.

### What to expect

- Acknowledgement within **72 hours**.
- Initial assessment within **7 days**.
- Coordinated disclosure: I'll keep you in the loop as a fix is prepared and
  agree on a public-disclosure date before publishing. For critical issues I
  aim to ship a fix within 14 days.

## Scope

In-scope:

- Backend (`backend/`): auth, session handling, SQLCipher integration, API
  routes, import/export, embedding worker.
- Frontend (`frontend/`): auth flow, CSRF handling, cookie handling, SPA
  state management.
- Deployment templates in `deploy/` and `scripts/` when used as documented.
- Supply-chain issues in our direct dependencies (pinned via `pyproject.toml`
  and `package.json`).

Out of scope:

- Vulnerabilities in upstream LLM/STT/TTS/embedding providers you configure.
  Report those to the respective vendor.
- Issues that require physical access to the server or an already-compromised
  host.
- Denial of service by exhausting resources you fully control (send your own
  server 10k requests/second — that's on you).

## Hardening Notes for Operators

- Always set `APP_PASSWORD` to a strong value (the config validator rejects
  obvious weak defaults, but you should go beyond the minimum).
- Keep `DB_ENCRYPTION_KEY`, `SESSION_SECRET`, `SECRET_KEY_WRAP` secret. Losing
  `DB_ENCRYPTION_KEY` means losing all entries — there is no recovery.
- Place the app behind TLS. The bundled Caddy config does this automatically
  when you set `DOMAIN` to a real hostname.
- For additional defense-in-depth, consider an SSO gateway (Cloudflare
  Access, Authelia, Pomerium) in front of the app.
