function getCsrf(): string {
  if (typeof document === "undefined") return "";
  return document.cookie.match(/(?:^|;\s*)csrf=([^;]*)/)?.[1] ?? "";
}

export async function* streamChat(
  messages: { role: string; content: string }[],
): AsyncGenerator<string> {
  const res = await fetch("/api/chat", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": getCsrf(),
    },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok || !res.body) throw new Error(`chat failed: ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const f of frames) {
      if (!f.startsWith("data: ")) continue;
      const payload = f.slice(6);
      if (payload === "[DONE]") return;
      // Server JSON-encodes each token so newlines survive SSE framing.
      try {
        yield JSON.parse(payload) as string;
      } catch {
        // Backwards-compat: tolerate unencoded payloads.
        yield payload;
      }
    }
  }
}

export async function finalize(
  messages: { role: string; content: string }[],
): Promise<{ title: string; content: string; tags: string[]; entry_date: string }> {
  const res = await fetch("/api/chat/finalize", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": getCsrf(),
    },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error(`finalize failed: ${res.status}`);
  return await res.json();
}
