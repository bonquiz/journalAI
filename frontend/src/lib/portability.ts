/** Portabilitäts-API: Export (Download via Anchor-Tag) + Import (multipart POST). */

export type ImportMode = "skip" | "copy" | "overwrite";

export type ImportResult = {
  dry_run: boolean;
  mode: ImportMode;
  total_in_file: number;
  new_entries: number;
  conflicts: number;
  would_apply: number;
  tags_new: number;
  tags_merged: number;
  errors: { index: number; id: string | null; reason: string }[];
};

export function exportUrl(): string {
  return "/api/export";
}

function getCsrf(): string {
  const m = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function importZip(
  file: File,
  mode: ImportMode,
  dryRun: boolean,
): Promise<ImportResult> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("mode", mode);
  fd.append("dry_run", dryRun ? "true" : "false");

  const resp = await fetch("/api/import", {
    method: "POST",
    body: fd,
    headers: { "x-csrf-token": getCsrf() },
    credentials: "include",
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
    throw new Error(body.detail ?? `HTTP ${resp.status}`);
  }
  return await resp.json();
}
