<script lang="ts">
  import { goto } from "$app/navigation";
  import { exportUrl, importZip, type ImportMode, type ImportResult } from "$lib/portability";
  import { toast } from "$lib/stores/toast";

  let file = $state<File | null>(null);
  let mode = $state<ImportMode>("skip");
  let preview = $state<ImportResult | null>(null);
  let importing = $state(false);
  let localError = $state<string | null>(null);

  async function onFileChange(ev: Event) {
    const input = ev.target as HTMLInputElement;
    file = input.files?.[0] ?? null;
    preview = null;
    localError = null;
    if (!file) return;
    try {
      preview = await importZip(file, mode, true);
    } catch (e) {
      localError = `Vorschau fehlgeschlagen: ${(e as Error).message}`;
    }
  }

  async function onModeChange() {
    if (!file) return;
    try {
      preview = await importZip(file, mode, true);
      localError = null;
    } catch (e) {
      localError = `Vorschau fehlgeschlagen: ${(e as Error).message}`;
    }
  }

  async function runImport() {
    if (!file) return;
    importing = true;
    localError = null;
    try {
      const result = await importZip(file, mode, false);
      toast.success(
        `Import abgeschlossen — ${result.new_entries} neu, ${result.conflicts} Konflikte (Modus: ${result.mode})`,
      );
      preview = result;
      await goto("/entries");
    } catch (e) {
      const msg = (e as Error).message;
      toast.error(`Import fehlgeschlagen: ${msg}`);
      localError = msg;
    } finally {
      importing = false;
    }
  }

  function wouldApplyLabel(p: ImportResult | null, m: ImportMode): string {
    if (!p) return "";
    if (m === "skip") return `${p.new_entries} Einträge werden geschrieben, ${p.conflicts} übersprungen.`;
    if (m === "copy") return `${p.new_entries} neu + ${p.conflicts} als Kopie = ${p.would_apply} Einträge.`;
    return `${p.new_entries} neu + ${p.conflicts} überschrieben = ${p.would_apply} Einträge.`;
  }
</script>

<section class="card">
  <h2>Datenportabilität</h2>

  <div class="block">
    <h3>Export</h3>
    <p class="muted">
      Lade alle Einträge und Tags als ZIP mit <code>entries.json</code> (Format v1) herunter.
    </p>
    <a class="btn" href={exportUrl()} download>Export herunterladen (.zip)</a>
  </div>

  <div class="block">
    <h3>Import</h3>
    <p class="muted">
      Lade ein Export-ZIP hoch. Nach Auswahl siehst du eine Vorschau.
    </p>

    <label class="file-label">
      ZIP wählen
      <input type="file" accept=".zip,application/zip" onchange={onFileChange} />
    </label>

    {#if preview}
      <div class="preview">
        <p><strong>{preview.total_in_file}</strong> Einträge in Datei, davon
          <strong>{preview.new_entries}</strong> neu,
          <strong>{preview.conflicts}</strong> Konflikte,
          <strong>{preview.tags_new}</strong> neue Tags.</p>

        <label>
          Konflikt-Modus:
          <select bind:value={mode} onchange={onModeChange}>
            <option value="skip">Überspringen</option>
            <option value="copy">Als Kopie importieren</option>
            <option value="overwrite">Überschreiben</option>
          </select>
        </label>

        <p class="muted">{wouldApplyLabel(preview, mode)}</p>

        <button
          type="button"
          class="btn"
          onclick={runImport}
          disabled={importing || !file}
        >
          {importing ? "Importiere…" : "Importieren"}
        </button>
      </div>
    {/if}

    {#if localError}<p class="error">{localError}</p>{/if}
  </div>
</section>

<style>
  .card {
    margin: 1rem 0;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .block { margin-bottom: 1rem; }
  .block:last-child { margin-bottom: 0; }
  h3 { margin: 0 0 0.35rem; font-size: 1rem; }
  .muted { color: var(--muted); font-size: 0.9em; margin: 0 0 0.6rem; }
  .btn {
    display: inline-block;
    padding: 0.6rem 1rem;
    min-height: 44px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: var(--radius);
    text-decoration: none;
    cursor: pointer;
  }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .file-label { display: block; margin: 0.5rem 0; }
  .preview {
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: #f3f4f6;
    border-radius: var(--radius);
  }
  .preview select { min-height: 36px; }
  .error { color: #b91c1c; }
</style>
