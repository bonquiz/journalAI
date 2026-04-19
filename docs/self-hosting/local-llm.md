# Lokaler LLM-Stack

journalAI kann komplett lokal betrieben werden, ohne OpenAI oder andere Cloud-Provider. Alle vier Capabilities (Chat, Embeddings, STT, TTS) laufen dann in Docker-Containern neben Backend und Frontend.

## Voraussetzungen

| | Minimal (CPU) | Recommended (GPU) |
|---|---|---|
| CPU | 8 Kerne dedicated | 4 Kerne |
| RAM | 16 GB | 16 GB |
| GPU | — | NVIDIA, ≥8 GB VRAM, Treiber ≥535, nvidia-container-toolkit |
| Disk | 20 GB (Modelle) | 50 GB (größere Modelle) |

## Schritte

1. **`.env.local-llm` anlegen:** `cp deploy/.env.local-llm.example deploy/.env.local-llm`, dann den passenden Tier-Block aktivieren.
2. **Stack starten:**
   ```bash
   # Minimal (CPU)
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
     --env-file deploy/.env --env-file deploy/.env.local-llm up -d

   # Recommended (GPU)
   docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.local-llm.yml \
     -f deploy/docker-compose.local-llm.gpu.yml \
     --env-file deploy/.env --env-file deploy/.env.local-llm up -d
   ```
3. **Erster Start (dauert 5-20 min):** `ollama-init` pullt die Modelle, speaches und Kokoro laden ihre Modelle beim ersten Request. Logs: `docker compose logs -f ollama-init`.
4. **Einloggen:** Backend bereitet `/api/settings` automatisch mit den ENV-Werten vor; in der UI siehst du die Hinweise „aus ENV: …".
5. **Testen:** Einen Voice-Eintrag aufnehmen oder eine semantische Suche starten. Falls ein Request mit 502 scheitert, in den Container-Logs nachsehen (häufig Modell-Pull läuft noch).

## FAQ

- **Kann ich Capabilities mischen?** Ja — einfach im Settings-UI für die gewünschte Capability einen anderen Endpoint/Model eintragen. DB schlägt ENV.
- **Wie wechsle ich das Chat-Modell?** `.env.local-llm` ändern, `docker compose up -d ollama-init` ausführen (pullt nur neue Modelle).
- **Warum ist mein Minimal-Tier so langsam?** Siehe `docs/benchmarks/` — CPU-only Chat bei 7B-Modellen ist inhärent langsam. Kleinere Modelle (3B, Q4) sind spürbar schneller.
