import { toast } from "$lib/stores/toast";

type CacheEntry = { blob: Blob; url: string };
const cache = new Map<string, CacheEntry>();

function csrf(): string {
  if (typeof document === "undefined") return "";
  return document.cookie.match(/(?:^|;\s*)csrf=([^;]*)/)?.[1] ?? "";
}

async function hashKey(text: string, voice?: string, speed?: number): Promise<string> {
  const material = `${text}|${voice ?? ""}|${speed ?? ""}`;
  const bytes = new TextEncoder().encode(material);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function synthesize(
  text: string,
  opts: { voice?: string; speed?: number } = {},
): Promise<CacheEntry | null> {
  const key = await hashKey(text, opts.voice, opts.speed);
  const hit = cache.get(key);
  if (hit) return hit;

  try {
    const res = await fetch("/api/tts", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf(),
      },
      body: JSON.stringify({ text, voice: opts.voice, speed: opts.speed }),
    });

    if (res.status === 401) {
      toast.error("Sitzung abgelaufen — bitte neu anmelden.");
      return null;
    }
    if (res.status === 403) {
      toast.error("CSRF-Token ungültig — Seite neu laden.");
      return null;
    }
    if (res.status === 422) {
      toast.error("Text zu lang oder ungültig für TTS (max. 20.000 Zeichen).");
      return null;
    }
    if (res.status === 429) {
      toast.error("Zu viele Vorlese-Anfragen — kurz warten.");
      return null;
    }
    if (res.status === 502) {
      let detail = "TTS-Endpoint nicht erreichbar oder fehlerhaft.";
      try {
        const body = await res.clone().json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* ignore parse error */
      }
      toast.error(detail);
      return null;
    }
    if (!res.ok) {
      toast.error("Vorlesen fehlgeschlagen — TTS-Endpoint prüfen.");
      return null;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const entry: CacheEntry = { blob, url };
    cache.set(key, entry);
    return entry;
  } catch {
    toast.error("Vorlesen fehlgeschlagen — TTS-Endpoint prüfen.");
    return null;
  }
}

export function clearCache(): void {
  for (const entry of cache.values()) {
    URL.revokeObjectURL(entry.url);
  }
  cache.clear();
}
