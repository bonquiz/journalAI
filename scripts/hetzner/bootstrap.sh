#!/usr/bin/env bash
# Bootstrap einer journalAI-Hetzner-Test-Instanz.
# Siehe docs/self-hosting/hetzner.md.
set -euo pipefail

TIER="minimal"
YES="false"
SSH_SOURCE_OVERRIDE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier) TIER="$2"; shift 2 ;;
    --yes) YES="true"; shift ;;
    --ssh-source-ip) SSH_SOURCE_OVERRIDE="$2"; shift 2 ;;
    *) echo "Unbekanntes Argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$TIER" == "minimal" || "$TIER" == "recommended" ]] || {
  echo "--tier muss 'minimal' oder 'recommended' sein" >&2; exit 2; }

# Repo-Root ermitteln (Skript liegt in scripts/hetzner/).
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

# ENV laden (nur wenn noch nicht gesetzt).
if [[ -f "$REPO_ROOT/deploy/.env.hetzner" ]]; then
  set -a; source "$REPO_ROOT/deploy/.env.hetzner"; set +a
fi

: "${HCLOUD_TOKEN:?HCLOUD_TOKEN fehlt (in deploy/.env.hetzner oder Shell)}"
: "${HCLOUD_SSH_KEY:?HCLOUD_SSH_KEY fehlt}"
HCLOUD_LOCATION="${HCLOUD_LOCATION:-nbg1}"
HCLOUD_SERVER_NAME="${HCLOUD_SERVER_NAME:-journalai-test}"
DOMAIN="${DOMAIN:-}"

command -v hcloud >/dev/null || { echo "hcloud CLI nicht installiert" >&2; exit 2; }
command -v rsync >/dev/null  || { echo "rsync nicht installiert" >&2; exit 2; }

export HCLOUD_TOKEN  # hcloud CLI liest HCLOUD_TOKEN aus ENV

# Lokale Env-Dateien prüfen.
[[ -f "$REPO_ROOT/deploy/.env" ]] || { echo "deploy/.env fehlt" >&2; exit 2; }
[[ -f "$REPO_ROOT/deploy/.env.local-llm" ]] || { echo "deploy/.env.local-llm fehlt" >&2; exit 2; }

# Server-Typ pro Tier.
case "$TIER" in
  minimal) SERVER_TYPE="cpx42" ;;         # 8 vCPU shared, 16 GB RAM, ~0,04 €/h (cpx41-Nachfolger)
  recommended)
    echo "FEHLER: Hetzner Cloud bietet aktuell keine GPU-Instances an (Stand 2026-04)." >&2
    echo "GPU-Tier erfordert Hetzner Robot (dedicated server) oder alternativen Provider." >&2
    echo "Siehe docs/self-hosting/hetzner.md." >&2
    exit 2 ;;
esac

echo ">> Ziel-Tier: $TIER ($SERVER_TYPE) in $HCLOUD_LOCATION"
if [[ "$YES" != "true" ]]; then
  read -r -p "Server jetzt anlegen? [y/N] " ans
  [[ "$ans" =~ ^[yY]$ ]] || { echo "Abbruch."; exit 0; }
fi

if [[ -n "$SSH_SOURCE_OVERRIDE" ]]; then
  SSH_SOURCE="$SSH_SOURCE_OVERRIDE"
else
  PUBLIC_IP="$(curl -sf https://ipv4.icanhazip.com || curl -sf https://api.ipify.org || curl -sf https://ifconfig.me)"
  [[ -n "$PUBLIC_IP" ]] || {
    echo "Konnte öffentliche IP nicht ermitteln. Nutze --ssh-source-ip <CIDR>." >&2; exit 1; }
  SSH_SOURCE="${PUBLIC_IP}/32"
fi

FW_NAME="${HCLOUD_SERVER_NAME}-fw"
if ! hcloud firewall describe "$FW_NAME" >/dev/null 2>&1; then
  echo ">> Firewall $FW_NAME anlegen (SSH nur von $SSH_SOURCE)"
  hcloud firewall create --name "$FW_NAME" >/dev/null
  hcloud firewall add-rule "$FW_NAME" --direction in --protocol tcp --port 22  --source-ips "$SSH_SOURCE"
  hcloud firewall add-rule "$FW_NAME" --direction in --protocol tcp --port 80  --source-ips "0.0.0.0/0,::/0"
  hcloud firewall add-rule "$FW_NAME" --direction in --protocol tcp --port 443 --source-ips "0.0.0.0/0,::/0"
fi

# Cloud-init schreiben.
CLOUD_INIT="$(mktemp)"
cat > "$CLOUD_INIT" <<CIEOF
#cloud-config
package_update: true
package_upgrade: false
packages:
  - ca-certificates
  - curl
  - git
  - jq
  - rsync
runcmd:
  - curl -fsSL https://get.docker.com | sh
  - usermod -aG docker ubuntu
CIEOF

if [[ "$TIER" == "recommended" ]]; then
  cat >> "$CLOUD_INIT" <<'CIEOF'
  - curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  - curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  - apt-get update && apt-get install -y nvidia-container-toolkit
  - nvidia-ctk runtime configure --runtime=docker
  - systemctl restart docker
CIEOF
fi

echo ">> Server $HCLOUD_SERVER_NAME erstellen"
hcloud server create \
  --name "$HCLOUD_SERVER_NAME" \
  --type "$SERVER_TYPE" \
  --image "ubuntu-24.04" \
  --location "$HCLOUD_LOCATION" \
  --ssh-key "$HCLOUD_SSH_KEY" \
  --firewall "$FW_NAME" \
  --user-data-from-file "$CLOUD_INIT" \
  --label "journalai=test" >/dev/null
rm -f "$CLOUD_INIT"

SERVER_IP="$(hcloud server ip "$HCLOUD_SERVER_NAME")"
echo ">> Server-IP: $SERVER_IP"

HOST="${DOMAIN:-${SERVER_IP}.sslip.io}"
echo ">> Host-URL: https://$HOST"

echo ">> Auf SSH warten"
for i in {1..60}; do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@$SERVER_IP" "cloud-init status --wait >/dev/null 2>&1 || true" </dev/null >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

echo ">> Code übertragen (rsync mit striktem Filter)"
rsync -az --delete --delete-excluded \
  --filter="merge $REPO_ROOT/scripts/hetzner/rsync-include.txt" \
  -e "ssh -o StrictHostKeyChecking=no" \
  "$REPO_ROOT/" "root@$SERVER_IP:/root/journalAI/"

echo ">> .env-Dateien explizit übertragen (nicht im Default-Filter)"
scp -o StrictHostKeyChecking=no \
  "$REPO_ROOT/deploy/.env" \
  "$REPO_ROOT/deploy/.env.local-llm" \
  "root@$SERVER_IP:/root/journalAI/deploy/"

echo ">> DOMAIN in deploy/.env setzen"
ssh -o StrictHostKeyChecking=no "root@$SERVER_IP" \
  "sed -i 's|^DOMAIN=.*|DOMAIN=${HOST}|' /root/journalAI/deploy/.env || echo 'DOMAIN=${HOST}' >> /root/journalAI/deploy/.env"

OVERLAYS=(-f docker-compose.yml -f docker-compose.local-llm.yml)
[[ "$TIER" == "recommended" ]] && OVERLAYS+=(-f docker-compose.local-llm.gpu.yml)

echo ">> Stack starten (${TIER})"
ssh -o StrictHostKeyChecking=no "root@$SERVER_IP" \
  "cd /root/journalAI/deploy && docker compose ${OVERLAYS[*]} --env-file .env --env-file .env.local-llm up -d"

echo ">> Auf /api/health warten (max. 10 min, erste Modell-Downloads brauchen Zeit)"
for i in {1..60}; do
  if curl -ksf "https://$HOST/api/health" >/dev/null; then
    echo ">> OK"
    break
  fi
  sleep 10
done

echo ""
echo "================ FERTIG ================"
echo "URL:       https://$HOST"
echo "SSH:       ssh root@$SERVER_IP"
echo "Teardown:  scripts/hetzner/teardown.sh"
echo "Kosten/h:  ≈0,04 € (cpx42)"
echo "========================================"
