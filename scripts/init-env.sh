#!/usr/bin/env bash
# Interactive first-time setup for journalAI.
# Generates deploy/.env with auto-rolled secrets and asks only the
# truly user-specific values. Idempotent-ish: won't overwrite an
# existing .env without confirmation.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/deploy/.env"
EXAMPLE_FILE="$REPO_ROOT/deploy/.env.example"

command -v openssl >/dev/null || {
  echo "FEHLER: 'openssl' wird benötigt um Secrets zu generieren." >&2
  echo "ERROR: 'openssl' is required to generate secrets." >&2
  exit 2
}

if [[ -f "$ENV_FILE" ]]; then
  echo "deploy/.env existiert bereits. / deploy/.env already exists."
  read -r -p "Overwrite? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "Aborted."; exit 0; }
  cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%s)"
  echo "  (Backup saved as $ENV_FILE.backup.*)"
fi

[[ -f "$EXAMPLE_FILE" ]] || {
  echo "FEHLER: $EXAMPLE_FILE fehlt." >&2
  exit 2
}

echo ""
echo "== journalAI setup =="
echo ""
read -r -p "Domain (e.g. journal.example.com, or 'localhost' for HTTP-only dev) [localhost]: " DOMAIN
DOMAIN="${DOMAIN:-localhost}"

while true; do
  read -r -s -p "App password (you'll use this to log in): " APP_PASSWORD
  echo
  if [[ ${#APP_PASSWORD} -lt 8 ]]; then
    echo "  Password must be at least 8 characters."
    continue
  fi
  read -r -s -p "Confirm password: " APP_PASSWORD2
  echo
  [[ "$APP_PASSWORD" == "$APP_PASSWORD2" ]] && break
  echo "  Passwords don't match. Try again."
done

echo ""
echo "Choose your LLM setup:"
echo "  1) OpenAI (just one API key, nothing else — recommended for first-time users)"
echo "  2) Any other OpenAI-compatible provider (Groq, Together, Anthropic via proxy, ...)"
echo "  3) Fully local (no cloud — you configure endpoints later per docs/self-hosting/local-llm.md)"
echo ""
read -r -p "Choice [1]: " LLM_CHOICE
LLM_CHOICE="${LLM_CHOICE:-1}"

OPENAI_API_KEY=""
case "$LLM_CHOICE" in
  1)
    read -r -s -p "OpenAI API key (sk-...): " OPENAI_API_KEY
    echo
    [[ -n "$OPENAI_API_KEY" ]] || {
      echo "  No key entered; you can add OPENAI_API_KEY to $ENV_FILE later."
    }
    ;;
  2)
    echo "  After setup: edit $ENV_FILE and set per-capability BASE_URL / API_KEY / MODEL."
    echo "  See docs/endpoint-compatibility.md for provider-specific recipes."
    ;;
  3)
    echo "  After setup: copy deploy/.env.local-llm.example to deploy/.env.local-llm,"
    echo "  then follow docs/self-hosting/local-llm.md to start the LLM overlay."
    ;;
  *)
    echo "  Unknown choice — leaving endpoint fields blank. Configure later in $ENV_FILE."
    ;;
esac

echo ""
echo "Generating secrets (64-hex, one-time)..."
DB_ENCRYPTION_KEY="$(openssl rand -hex 32)"
SESSION_SECRET="$(openssl rand -hex 32)"
SECRET_KEY_WRAP="$(openssl rand -hex 32)"

python3 - "$EXAMPLE_FILE" "$ENV_FILE" \
  "$DOMAIN" "$APP_PASSWORD" \
  "$DB_ENCRYPTION_KEY" "$SESSION_SECRET" "$SECRET_KEY_WRAP" \
  "$OPENAI_API_KEY" <<'PYEOF'
import sys, re
ex, env, domain, pw, dek, ses, skw, openai_key = sys.argv[1:]
with open(ex) as f: src = f.read()
def sub(pat, val):
    global src
    # match "KEY=..." on a single line (allow CHANGE_ME placeholder and plain empty)
    src = re.sub(rf'(?m)^{pat}=.*$', f'{pat}={val}', src)
sub('DOMAIN', domain)
sub('APP_PASSWORD', pw)
sub('DB_ENCRYPTION_KEY', dek)
sub('SESSION_SECRET', ses)
sub('SECRET_KEY_WRAP', skw)
if openai_key:
    sub('OPENAI_API_KEY', openai_key)
with open(env, 'w') as f: f.write(src)
PYEOF

chmod 600 "$ENV_FILE"

echo ""
echo "✅ $ENV_FILE written (mode 600)."
echo ""
echo "Next:"
case "$LLM_CHOICE" in
  1|2)
    echo "  docker compose -f deploy/docker-compose.yml up -d"
    ;;
  3)
    echo "  cp deploy/.env.local-llm.example deploy/.env.local-llm"
    echo "  # edit .env.local-llm to pick the tier (minimal/recommended)"
    echo "  docker compose -f deploy/docker-compose.yml \\"
    echo "    -f deploy/docker-compose.local-llm.yml \\"
    echo "    --env-file deploy/.env --env-file deploy/.env.local-llm up -d"
    ;;
esac
echo ""
echo "Then open https://$DOMAIN and log in with the app password you set."
if [[ "$DOMAIN" == "localhost" ]]; then
  echo "(Localhost uses HTTP on :443 with a self-signed cert — accept the warning.)"
fi
