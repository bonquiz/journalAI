---
date: 2026-04-19
tier: recommended
label: runpod-rtx4090
provider: RunPod Community Cloud
gpu: NVIDIA GeForce RTX 4090 (24 GB VRAM)
chat_tokens_per_second: 157.9
chat_chars_per_second: 638.61
embed_entries_per_second_bge_m3: 1.7
---

# Benchmark 2026-04-19 — recommended — RunPod RTX 4090

Gemessen gegen nativ installiertes Ollama (nicht volles Compose-Stack) — RunPod Community Pods erlauben kein Docker-in-Docker ohne `--privileged`. STT/TTS liefen weiter auf dem Hetzner-cpx42-Sidecar via SSH-Tunnel, weshalb hier nur Chat/Embed gemessen wurden.

| Metric | Value | Modell |
|---|---|---|
| Chat tokens/s (pure eval) | **157.9** | qwen2.5:7b-instruct-q4_K_M |
| Chat chars/s | **638.6** | dito |
| Embed entries/s (sequentiell) | 1.7 | bge-m3 |

## Kontext

- **Prompt:** „Schreibe einen ca. 500 Wörter langen, zusammenhängenden deutschen Text über die Bedeutung von Datenschutz im Alltag."
- **Output:** 903 Tokens in 5,72s Eval-Zeit (3652 Zeichen). Grammatikalisch einwandfrei, zusammenhängend.
- **Vergleich:** Minimal-Tier (cpx42 + qwen2.5:3b) ~15 tok/s → GPU mit **doppelt so großem Modell** ~10× schneller.

## Embed-Nebenergebnis

`bge-m3` ist mächtiger (1024-dim, multilingual) aber Ollama's Embed-API serialisiert; 1,7 seq-entries/s sind nicht direkt mit Minimal-Tier (`nomic-embed-text` 3,5/s) vergleichbar. Für faire Zahlen bräuchte es parallele Batching-Messungen.

## User-Experience-Test (qwen2.5:14b-instruct-q4_K_M)

Anschließend qwen2.5:**14b** geladen (9 GB VRAM) und im Browser getestet:
- Deutlicher Qualitätssprung gegenüber 3b/7b (Grammatik, Wortwahl, Kohärenz)
- Streaming-Antwortzeit durch Hetzner-Tunnel ~2-4s für typische Tagebuch-Dialog-Antwort

## Setup

- Pod deployment: `podFindAndDeployOnDemand` GraphQL mutation, Image `runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04`
- Ollama-Install: `curl -fsSL https://ollama.com/install.sh | sh` (plus `apt-get install zstd pciutils`)
- Ollama-Start: `ollama serve` als Nohup-Process (kein systemd in Container)
- Kosten: $0.34/h on-demand, gesamter Test ~45 min = ~$0.25
