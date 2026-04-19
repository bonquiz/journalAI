# journalAI auf Hetzner Cloud (B-Pfad)

Wenn du selbst keine geeignete Hardware hast, kannst du den lokalen LLM-Stack temporär auf einem Hetzner-Cloud-Server betreiben — stundenweise gemietet, danach wieder abgerissen.

## Voraussetzungen

- Hetzner-Cloud-Account
- `hcloud` CLI installiert (`brew install hcloud` / `apt install hcloud-cli` / von Hetzner-GitHub)
- Ein SSH-Public-Key in HCloud hochgeladen (`hcloud ssh-key create --name julian-key --public-key-from-file ~/.ssh/id_ed25519.pub`)
- API-Token (Read+Write) aus der HCloud-Console

## Setup

1. Vorlage kopieren und füllen:
   ```bash
   cp deploy/.env.hetzner.example deploy/.env.hetzner
   # HCLOUD_TOKEN + HCLOUD_SSH_KEY eintragen
   ```
2. `deploy/.env` und `deploy/.env.local-llm` lokal vorbereiten (siehe `docs/self-hosting/local-llm.md`).
3. Bootstrap:
   ```bash
   # Kurztest, CPU-only, ~0,03 €/h
   ./scripts/hetzner/bootstrap.sh --tier minimal

   # Brauchbare Chat-Qualität, GPU, ~1,05 €/h
   ./scripts/hetzner/bootstrap.sh --tier recommended
   ```
4. Das Skript gibt am Ende die URL aus (Form: `https://<ip>.sslip.io`). Der erste Login-Flow geht ganz normal über das UI.
5. Abreißen:
   ```bash
   ./scripts/hetzner/teardown.sh
   ```

## Kosten (Stand 2026-04)

| Tier | Server-Typ | ~ Kosten/h | Typische Test-Laufzeit |
|---|---|---|---|
| Minimal | cpx41 | 0,03 € | 1-4 h |
| Recommended | gex44 | 1,05 € | 30-120 min |

## Maximal abgeschottet (Tailscale)

Die Default-Firewall öffnet Port 443 fürs offene Internet. Wer das nicht will, nimmt den öffentlichen Zugang auf den Server ganz vom Netz und erreicht ihn nur noch über Tailscale.

**Wichtiger Hinweis zur Architektur:** Tailscale-Verkehr kommt **nicht** als Pakete mit Source-IP `100.64/10` an der HCloud-Firewall an — Tailscale tunnelt über WireGuard auf UDP 41641 und die Pakete erscheinen an `tailscale0` intern auf dem Server. Die HCloud-Firewall via `--source-ips 100.64.0.0/10` einschränken zu wollen funktioniert daher **nicht**. Stattdessen:

1. Auf dem Server (via SSH):
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
2. Lokal (Client) dasselbe: `tailscale up`.
3. HCloud-Firewall: Port 443 komplett entfernen (nicht einschränken). Tailscale selbst braucht keine HCloud-Firewall-Regel — die WireGuard-Pakete kommen auf allen Ports durch NAT-Hole-Punching an.
   ```bash
   hcloud firewall replace-rules journalai-test-fw --rules-file <(cat <<EOF
   [
     {"direction":"in","protocol":"tcp","port":"22","source_ips":["$(curl -s ifconfig.me)/32"]}
   ]
   EOF
   )
   ```
4. Caddy-Binding auf das Tailscale-Interface beschränken, damit es nichts mehr auf der öffentlichen IP hört:
   - Variante a (minimal): auf dem Server `docker compose restart caddy` entfällt — stattdessen Caddy-Container-Port-Mapping einschränken: in einer Override-Compose-Datei nur `tailscale0`-IP binden, z. B. `ports: ["100.x.y.z:443:443"]` (Tailscale-IP via `tailscale ip -4` ermitteln).
   - Variante b: Auf Caddy-HTTPS verzichten und über Tailscale-MagicDNS auf den Backend-Container tunneln (`tailscale serve`).
5. Zugriff dann nur noch über den Tailscale-Hostnamen/IP des Servers, z. B. `https://journalai-test.tail-xxxx.ts.net/` (MagicDNS aktiviert) oder `https://100.x.y.z/` mit selbst-signiertem Cert.

Tailscale-Auth-Keys bleiben bewusst außerhalb von `.env.hetzner` (eigener Login-Flow per Browser oder `tailscale up --authkey`).

**Wenn nur SSH-Lockdown gewünscht ist** (ohne Tailscale-Gesamtlösung): einfacher `hcloud firewall replace-rules` wie oben, der nur Port 22 von der eigenen IP erlaubt — 80/443 werden komplett geschlossen, Server ist dann nur noch über SSH-Portforward erreichbar (`ssh -L 8443:localhost:443 root@<ip>`).

## Wechselnde Client-IP

`bootstrap.sh` öffnet SSH nur von deiner aktuellen öffentlichen IP. Wenn du VPN umschaltest oder in ein anderes Netz wechselst, musst du die Regel updaten:

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
