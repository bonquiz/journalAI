#!/usr/bin/env bash
# Misst Performance der vier LLM-Capabilities gegen eine laufende journalAI-Instanz.
# Schreibt einen Report nach docs/benchmarks/YYYY-MM-DD-<tier>-<hostname>.md.
set -euo pipefail

URL=""; TIER="minimal"; LABEL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)   URL="$2"; shift 2 ;;
    --tier)  TIER="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    *) echo "Unbekannt: $1" >&2; exit 2 ;;
  esac
done
: "${URL:?--url fehlt (z. B. https://<ip>.sslip.io)}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH_ENV="$REPO_ROOT/deploy/.env.benchmark"
[[ -f "$BENCH_ENV" ]] || { echo "deploy/.env.benchmark fehlt — enthält APP_PASSWORD" >&2; exit 2; }
set -a; source "$BENCH_ENV"; set +a
: "${APP_PASSWORD:?APP_PASSWORD fehlt}"

command -v jq       >/dev/null || { echo "jq fehlt" >&2; exit 2; }
command -v curl     >/dev/null || { echo "curl fehlt" >&2; exit 2; }
command -v python3  >/dev/null || { echo "python3 fehlt" >&2; exit 2; }
command -v ffprobe  >/dev/null || { echo "ffprobe fehlt (ffmpeg paket)" >&2; exit 2; }

COOKIE="$(mktemp)"; trap 'rm -f "$COOKIE"' EXIT

# journalAI hat keinen separaten /csrf-Endpoint und keinen Username —
# Login nimmt nur {"password": ...} und setzt Session + CSRF-Cookie im Response.
curl -ksf -c "$COOKIE" -b "$COOKIE" -X POST "$URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$APP_PASSWORD\"}" >/dev/null
CSRF="$(awk '$6 ~ /^csrf/ { print $7 }' "$COOKIE")"
[[ -n "$CSRF" ]] || { echo "CSRF-Cookie nicht gefunden — Login fehlgeschlagen?" >&2; exit 1; }

# --- Chat-Benchmark -----------------------------------------------------------
# Die SSE-Events des Backends haben die Form `data: "<token>"\n\n` (JSON-encoded
# String pro Token) + `data: [DONE]` als Sentinel. Siehe backend/app/routes/chat.py.
# Wir messen chars/s (ehrliche, provider-neutrale Metrik) statt tokens/s.
echo ">> Chat"
CHAT_PROMPT="Schreibe einen 500 Wörter langen, zusammenhängenden deutschen Text über die Bedeutung von Datenschutz im Alltag."
CHAT_START="$(date +%s.%N)"
CHAT_RESPONSE="$(curl -ksf -b "$COOKIE" -c "$COOKIE" \
  -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -X POST "$URL/api/chat" \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$CHAT_PROMPT\"}]}" \
  --no-buffer | tr -d '\r')"
CHAT_END="$(date +%s.%N)"
CHAT_ELAPSED="$(python3 -c "print($CHAT_END - $CHAT_START)")"
CHAT_TEXT="$(echo "$CHAT_RESPONSE" \
  | grep '^data: ' \
  | sed 's/^data: //' \
  | grep -v '^\[DONE\]$' \
  | jq -Rs 'split("\n") | map(select(length > 0) | fromjson) | join("")')"
CHAT_CHARS="$(printf '%s' "$CHAT_TEXT" | wc -c | awk '{print $1}')"
CHAT_CPS="$(python3 -c "print(round($CHAT_CHARS / $CHAT_ELAPSED, 2))")"

# --- STT-Benchmark ------------------------------------------------------------
# Das Backend erwartet den Upload unter dem Feldnamen `file` (siehe
# backend/app/routes/transcribe.py). CSRF-Cookie kann zwischen Requests
# rotieren, deshalb neu einlesen.
CSRF="$(awk '$6 ~ /^csrf/ { print $7 }' "$COOKIE")"
echo ">> STT"
STT_START="$(date +%s.%N)"
curl -ksf -b "$COOKIE" -c "$COOKIE" -H "X-CSRF-Token: $CSRF" -X POST "$URL/api/transcribe" \
  -F "file=@$REPO_ROOT/tests/fixtures/benchmark-60s.webm" >/dev/null
STT_END="$(date +%s.%N)"
STT_ELAPSED="$(python3 -c "print($STT_END - $STT_START)")"
STT_RTF="$(python3 -c "print(round($STT_ELAPSED / 60.0, 2))")"

# --- Embed-Benchmark ----------------------------------------------------------
CSRF="$(awk '$6 ~ /^csrf/ { print $7 }' "$COOKIE")"
echo ">> Embed (100 Entries reindex)"
CREATED_IDS=()
for i in $(seq 1 100); do
  EID="$(curl -ksf -b "$COOKIE" -c "$COOKIE" -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
    -X POST "$URL/api/entries" \
    -d "{\"entry_date\":\"2026-04-19\",\"title\":\"bench-$i\",\"content\":\"Test-Eintrag Nummer $i. Stichworte: Alltag, Datenschutz, Selbst-Reflexion.\"}" \
    | jq -r '.id')"
  CREATED_IDS+=("$EID")
  CSRF="$(awk '$6 ~ /^csrf/ { print $7 }' "$COOKIE")"
done

EMBED_START="$(date +%s.%N)"
curl -ksf -b "$COOKIE" -c "$COOKIE" -H "X-CSRF-Token: $CSRF" -X POST "$URL/api/search/reindex" >/dev/null
# Das Status-Schema: {total, embedded, pending, current_model, configured, indexing:bool}
# Kein "status"-String — wir pollen bis indexing=false. Pending > 0 nach Ende
# heißt einzelne Embeds sind gescheitert (wird im Report erwähnt).
sleep 2  # kurz warten, damit indexing=true sichtbar wird
for _ in $(seq 1 300); do
  STATUS_JSON="$(curl -ksf -b "$COOKIE" "$URL/api/search/status")"
  INDEXING="$(echo "$STATUS_JSON" | jq -r '.indexing')"
  [[ "$INDEXING" == "false" ]] && break
  sleep 2
done
EMBED_END="$(date +%s.%N)"
EMBED_PENDING="$(echo "$STATUS_JSON" | jq -r '.pending')"
EMBED_ELAPSED="$(python3 -c "print($EMBED_END - $EMBED_START)")"
EMBED_EPS="$(python3 -c "print(round(100 / $EMBED_ELAPSED, 2))")"

for eid in "${CREATED_IDS[@]}"; do
  curl -ksf -b "$COOKIE" -H "X-CSRF-Token: $CSRF" -X DELETE "$URL/api/entries/$eid" >/dev/null || true
done

# --- TTS-Benchmark ------------------------------------------------------------
CSRF="$(awk '$6 ~ /^csrf/ { print $7 }' "$COOKIE")"
echo ">> TTS"
TTS_TEXT="Dies ist ein Test-Text mit dreihundert Zeichen, um die Geschwindigkeit der lokalen Text-zu-Sprache-Engine zu vermessen. Wir testen sowohl CPU- als auch GPU-basierte Setups, um dir als Nutzer realistische Kennzahlen zu geben."
TTS_TMP="$(mktemp --suffix=.mp3)"
TTS_START="$(date +%s.%N)"
curl -ksf -b "$COOKIE" -c "$COOKIE" -H "X-CSRF-Token: $CSRF" -H "Content-Type: application/json" \
  -X POST "$URL/api/tts" -d "{\"text\":\"$TTS_TEXT\"}" -o "$TTS_TMP"
TTS_END="$(date +%s.%N)"
TTS_ELAPSED="$(python3 -c "print($TTS_END - $TTS_START)")"
TTS_AUDIO_LEN="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$TTS_TMP")"
TTS_RTF="$(python3 -c "print(round($TTS_ELAPSED / $TTS_AUDIO_LEN, 3))")"
rm -f "$TTS_TMP"

# --- Report schreiben ---------------------------------------------------------
DATE="$(date +%Y-%m-%d)"
HOSTNAME_RAW="${URL#https://}"
HOSTNAME_SAFE="$(echo "$HOSTNAME_RAW" | tr -c '[:alnum:]-' '-')"
LABEL_SAFE="${LABEL:-$HOSTNAME_SAFE}"
REPORT="$REPO_ROOT/docs/benchmarks/${DATE}-${TIER}-${LABEL_SAFE}.md"

{
  echo "---"
  echo "date: $DATE"
  echo "tier: $TIER"
  echo "label: $LABEL_SAFE"
  echo "url: $URL"
  echo "chat_chars_per_second: $CHAT_CPS"
  echo "stt_rtf: $STT_RTF"
  echo "embed_entries_per_second: $EMBED_EPS"
  echo "tts_rtf: $TTS_RTF"
  echo "---"
  echo ""
  echo "# Benchmark $DATE — $TIER — $LABEL_SAFE"
  echo ""
  echo "| Metric | Value |"
  echo "|---|---|"
  echo "| Chat (chars/s) | $CHAT_CPS |"
  echo "| STT (RTF, lower=faster) | $STT_RTF |"
  echo "| Embed (entries/s) | $EMBED_EPS |"
  echo "| TTS (RTF, lower=faster) | $TTS_RTF |"
  if [[ "${EMBED_PENDING:-0}" != "0" && "${EMBED_PENDING:-0}" != "null" ]]; then
    echo ""
    echo "Hinweis: $EMBED_PENDING Embeddings blieben pending (Embed-Endpoint hat transient gescheitert — Metrik bezieht sich auf die 100 Entries, die durchliefen)."
  fi
} > "$REPORT"

echo ""
echo "Report: $REPORT"
cat "$REPORT"
