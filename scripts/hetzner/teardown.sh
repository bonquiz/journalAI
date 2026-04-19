#!/usr/bin/env bash
# Räumt die von bootstrap.sh angelegten HCloud-Ressourcen auf.
set -euo pipefail

YES="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES="true"; shift ;;
    *) echo "Unbekanntes Argument: $1" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -f "$REPO_ROOT/deploy/.env.hetzner" ]] && { set -a; source "$REPO_ROOT/deploy/.env.hetzner"; set +a; }

: "${HCLOUD_TOKEN:?HCLOUD_TOKEN fehlt}"
HCLOUD_SERVER_NAME="${HCLOUD_SERVER_NAME:-journalai-test}"
FW_NAME="${HCLOUD_SERVER_NAME}-fw"
export HCLOUD_TOKEN

if [[ "$YES" != "true" ]]; then
  read -r -p "Server '$HCLOUD_SERVER_NAME' und Firewall '$FW_NAME' wirklich löschen? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "Abbruch."; exit 0; }
fi

if hcloud server describe "$HCLOUD_SERVER_NAME" >/dev/null 2>&1; then
  hcloud server delete "$HCLOUD_SERVER_NAME"
  echo ">> Server gelöscht"
else
  echo ">> Server '$HCLOUD_SERVER_NAME' existiert nicht — übersprungen"
fi

if hcloud firewall describe "$FW_NAME" >/dev/null 2>&1; then
  hcloud firewall delete "$FW_NAME"
  echo ">> Firewall gelöscht"
else
  echo ">> Firewall '$FW_NAME' existiert nicht — übersprungen"
fi
