# journalAI on Hetzner Cloud (Path B)

🇩🇪 [Deutsche Version](hetzner.de.md)

If you don't have suitable hardware of your own, you can run the local LLM stack on a temporary Hetzner Cloud server — rented by the hour, torn down when done.

## Prerequisites

- Hetzner Cloud account
- `hcloud` CLI installed (`brew install hcloud` / `apt install hcloud-cli` / from Hetzner GitHub)
- An SSH public key uploaded to HCloud (`hcloud ssh-key create --name my-key --public-key-from-file ~/.ssh/id_ed25519.pub`)
- API token (Read+Write) from the HCloud console

## Setup

1. Copy the template and fill it:
   ```bash
   cp deploy/.env.hetzner.example deploy/.env.hetzner
   # Set HCLOUD_TOKEN + HCLOUD_SSH_KEY
   ```
2. Prepare `deploy/.env` and `deploy/.env.local-llm` locally (see [`local-llm.md`](local-llm.md)).
3. Bootstrap:
   ```bash
   # CPU-only short test, ~0.04 €/h
   ./scripts/hetzner/bootstrap.sh --tier minimal
   ```
4. The script prints the URL at the end (form: `https://<ip>.sslip.io`). Log in via the UI with your app password.
5. Tear down:
   ```bash
   ./scripts/hetzner/teardown.sh
   ```

## Costs (as of 2026-04)

| Tier | Server type | ~ Cost/h | Typical test runtime |
|---|---|---|---|
| Minimal | cpx42 | 0.04 € | 1–4 h |

## GPU tier — not on Hetzner Cloud

As of April 2026, **Hetzner Cloud offers no GPU instances**. The GEX-series is a **Hetzner Robot** (dedicated-server) product — separate API, noticeably longer minimum billing cycles, no true on-demand hourly rentals like HCloud.

For the GPU test tier ("Recommended"), we suggest alternatives:
- **Hetzner Robot** — dedicated GPU servers, ordered via web console or Robot API. Mind minimum rental periods and setup fees.
- **Paperspace / Lambda / RunPod / Vast.ai** — pay-per-hour GPU cloud. Our `docker-compose.local-llm.gpu.yml` overlay runs as-is if `nvidia-container-toolkit` is installed on the host.

The bootstrap script's `--tier recommended` flag therefore currently errors out and points here.

## Maximum lockdown (Tailscale)

The default firewall exposes port 443 to the public internet. If you don't want that, put Tailscale in front and close 443 entirely.

**Important architecture note:** Tailscale traffic does **not** arrive at the HCloud firewall as packets with source IP `100.64/10`. Tailscale tunnels via WireGuard on UDP 41641 and the packets surface on `tailscale0` *inside* the server. Trying to restrict the HCloud firewall with `--source-ips 100.64.0.0/10` therefore **does not work**. Instead:

1. On the server (via SSH):
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
2. On your local machine: `tailscale up`.
3. HCloud firewall: remove port 443 entirely (don't try to restrict by source). Tailscale needs no HCloud firewall rule — WireGuard punches through NAT on any port.
   ```bash
   hcloud firewall replace-rules journalai-test-fw --rules-file <(cat <<EOF
   [
     {"direction":"in","protocol":"tcp","port":"22","source_ips":["$(curl -s ifconfig.me)/32"]}
   ]
   EOF
   )
   ```
4. Bind Caddy to the Tailscale interface only so it no longer listens on the public IP:
   - Option A (minimal): in an override compose file, bind Caddy's port only to the Tailscale IP, e.g. `ports: ["100.x.y.z:443:443"]` (get the Tailscale IP via `tailscale ip -4`).
   - Option B: drop Caddy's HTTPS and tunnel via Tailscale MagicDNS directly to the backend (`tailscale serve`).
5. Access then only via the server's Tailscale hostname/IP, e.g. `https://journalai-test.tail-xxxx.ts.net/` (if MagicDNS enabled) or `https://100.x.y.z/` with a self-signed cert.

Tailscale auth keys are deliberately kept out of `.env.hetzner` — they have their own login flow (browser-based or `tailscale up --authkey`).

**If you just want SSH lockdown** (without a full Tailscale setup): a simpler `hcloud firewall replace-rules` that only allows port 22 from your IP — ports 80/443 closed entirely, server reachable only via SSH port-forward (`ssh -L 8443:localhost:443 root@<ip>`).

## Changing client IP

`bootstrap.sh` only opens SSH from your current public IP. If you switch VPN or networks, update the rule:

```bash
MY_IP="$(curl -s ifconfig.me)/32"
hcloud firewall replace-rules journalai-test-fw --rules-file <(cat <<EOF
[
  {"direction":"in","protocol":"tcp","port":"22","source_ips":["$MY_IP"]},
  {"direction":"in","protocol":"tcp","port":"80","source_ips":["0.0.0.0/0","::/0"]},
  {"direction":"in","protocol":"tcp","port":"443","source_ips":["0.0.0.0/0","::/0"]}
]
EOF
)
```
