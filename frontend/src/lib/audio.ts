export class Recorder {
  private rec: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  async start(): Promise<void> {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.chunks = [];
    this.rec = new MediaRecorder(stream);
    this.rec.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    this.rec.start();
  }

  async stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.rec) { resolve(new Blob()); return; }
      this.rec.onstop = () => {
        this.rec?.stream.getTracks().forEach((t) => t.stop());
        const type = this.rec?.mimeType ?? "audio/webm";
        resolve(new Blob(this.chunks, { type }));
      };
      this.rec.stop();
    });
  }
}

function getCsrf(): string {
  if (typeof document === "undefined") return "";
  return document.cookie.match(/(?:^|;\s*)csrf=([^;]*)/)?.[1] ?? "";
}

export async function transcribe(blob: Blob): Promise<string> {
  const form = new FormData();
  const ext = blob.type.includes("webm") ? "webm" : "wav";
  form.append("file", blob, `voice.${ext}`);
  const res = await fetch("/api/transcribe", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": getCsrf() },
    body: form,
  });
  if (!res.ok) throw new Error(`transcribe failed: ${res.status}`);
  const j = await res.json();
  return j.transcript;
}
