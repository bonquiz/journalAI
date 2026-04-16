<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import Spinner from "$lib/components/Spinner.svelte";

  type Stat = { name: string; count: number };

  let stats = $state<Stat[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error: string | null = $state(null);
  let info: string | null = $state(null);

  // Rename state
  let renamingTag = $state<string | null>(null);
  let renameValue = $state("");

  // Merge state
  let mergeSelection = $state<Set<string>>(new Set());
  let mergeTarget = $state("");

  async function load() {
    loading = true;
    try {
      stats = await api<Stat[]>("/api/tags/stats");
    } catch {
      error = "Tags konnten nicht geladen werden.";
    } finally {
      loading = false;
    }
  }
  onMount(load);

  function startRename(name: string) {
    renamingTag = name;
    renameValue = name;
    error = info = null;
  }

  async function saveRename() {
    if (!renamingTag) return;
    const newName = renameValue.trim().toLowerCase();
    if (!newName || newName === renamingTag) {
      renamingTag = null;
      return;
    }
    busy = true;
    try {
      await api(`/api/tags/${encodeURIComponent(renamingTag)}`, {
        method: "PUT",
        body: { new_name: newName },
      });
      info = `"${renamingTag}" → "${newName}"`;
      renamingTag = null;
      await load();
    } catch {
      error = "Umbenennen fehlgeschlagen.";
    } finally {
      busy = false;
    }
  }

  async function deleteTag(name: string) {
    if (!confirm(`Tag "${name}" löschen? Alle Zuordnungen gehen verloren.`)) return;
    busy = true;
    error = info = null;
    try {
      await api(`/api/tags/${encodeURIComponent(name)}`, { method: "DELETE" });
      info = `"${name}" gelöscht.`;
      await load();
    } catch {
      error = "Löschen fehlgeschlagen.";
    } finally {
      busy = false;
    }
  }

  function toggleMergeSource(name: string) {
    if (mergeSelection.has(name)) mergeSelection.delete(name);
    else mergeSelection.add(name);
    mergeSelection = new Set(mergeSelection);
  }

  async function runMerge() {
    const sources = Array.from(mergeSelection);
    const target = mergeTarget.trim().toLowerCase();
    if (!target) {
      error = "Zielname angeben.";
      return;
    }
    if (sources.length === 0) {
      error = "Mindestens ein Quell-Tag auswählen.";
      return;
    }
    if (!confirm(`${sources.length} Tag(s) in "${target}" zusammenführen?`)) return;
    busy = true;
    error = info = null;
    try {
      await api("/api/tags/merge", {
        method: "POST",
        body: { sources, target },
      });
      info = `Zusammengeführt in "${target}".`;
      mergeSelection = new Set();
      mergeTarget = "";
      await load();
    } catch {
      error = "Merge fehlgeschlagen.";
    } finally {
      busy = false;
    }
  }
</script>

<h1>Tags verwalten</h1>

{#if info}<p class="info">{info}</p>{/if}
{#if error}<p class="err">{error}</p>{/if}

{#if loading}
  <p class="loading"><Spinner /> <span>Lade Tags…</span></p>
{:else if stats.length === 0}
  <p class="muted">Noch keine Tags. Leg einen Eintrag an.</p>
{:else}
  <section class="merge-panel">
    <h2>Zusammenführen</h2>
    <p class="muted">
      Wähle Quell-Tags über die Kästchen und gib einen Zielnamen ein.
      Existiert der Zielname noch nicht, wird er erstellt.
    </p>
    <div class="merge-controls">
      <input
        bind:value={mergeTarget}
        placeholder="Ziel-Tag (neu oder existierend)"
        disabled={busy}
      />
      <button
        type="button"
        onclick={runMerge}
        disabled={busy || mergeSelection.size === 0 || !mergeTarget.trim()}
      >
        {#if busy}<Spinner /> Zusammenführen…{:else}
          Zusammenführen ({mergeSelection.size})
        {/if}
      </button>
    </div>
  </section>

  <table class="tag-table">
    <thead>
      <tr>
        <th class="col-sel">Merge</th>
        <th>Tag</th>
        <th class="col-count">Einträge</th>
        <th class="col-actions">Aktionen</th>
      </tr>
    </thead>
    <tbody>
      {#each stats as t (t.name)}
        <tr>
          <td class="col-sel">
            <input
              type="checkbox"
              checked={mergeSelection.has(t.name)}
              onchange={() => toggleMergeSource(t.name)}
              disabled={busy}
              aria-label={`${t.name} als Quelle für Merge auswählen`}
            />
          </td>
          <td>
            {#if renamingTag === t.name}
              <input
                bind:value={renameValue}
                onkeydown={(e) => {
                  if (e.key === "Enter") { e.preventDefault(); saveRename(); }
                  if (e.key === "Escape") renamingTag = null;
                }}
                disabled={busy}
                class="rename-input"
              />
            {:else}
              <span class="tag-name">{t.name}</span>
            {/if}
          </td>
          <td class="col-count">{t.count}</td>
          <td class="col-actions">
            {#if renamingTag === t.name}
              <button type="button" onclick={saveRename} disabled={busy}>Speichern</button>
              <button type="button" onclick={() => (renamingTag = null)} disabled={busy}>
                Abbrechen
              </button>
            {:else}
              <button type="button" onclick={() => startRename(t.name)} disabled={busy}>
                Umbenennen
              </button>
              <button
                type="button"
                onclick={() => deleteTag(t.name)}
                disabled={busy}
                class="danger"
              >
                Löschen
              </button>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  .info { color: var(--accent); }
  .err { color: #b22; }
  .muted { color: var(--muted); }
  .loading { display: flex; align-items: center; gap: 0.5rem; color: var(--muted); }

  .merge-panel {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 0.75rem 1rem;
    margin: 1rem 0;
    background: #fafbfc;
  }
  .merge-panel h2 { margin: 0 0 0.3rem; font-size: 1rem; }
  .merge-controls {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }
  .merge-controls input { flex: 1 1 12rem; min-width: 0; }
  .merge-controls button { min-height: 44px; }

  .tag-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 0.5rem;
  }
  .tag-table th, .tag-table td {
    padding: 0.6rem 0.4rem;
    border-bottom: 1px solid var(--border);
    text-align: left;
    vertical-align: middle;
  }
  .tag-table th {
    font-size: 0.85em;
    color: var(--muted);
    font-weight: 600;
  }
  .col-sel { width: 3.5rem; text-align: center; }
  .col-count { width: 5rem; text-align: right; }
  .col-actions { width: 14rem; }
  .col-actions button {
    min-height: 44px;
    margin-right: 0.25rem;
  }
  .col-actions .danger { background: #c33; }
  .tag-name { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .rename-input { width: 100%; min-width: 8rem; }

  input[type="checkbox"] {
    width: 20px;
    height: 20px;
    cursor: pointer;
  }

  @media (max-width: 640px) {
    .tag-table th, .tag-table td { padding: 0.5rem 0.25rem; }
    .col-actions { width: auto; }
    .col-actions button {
      display: block;
      width: 100%;
      margin: 0.2rem 0;
    }
    .rename-input { width: 100%; }
  }
</style>
