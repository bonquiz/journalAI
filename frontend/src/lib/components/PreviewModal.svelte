<script lang="ts">
  import Spinner from "./Spinner.svelte";
  import TagChip from "./TagChip.svelte";

  let {
    entry = $bindable(),
    saving = false,
    oncancel,
    onconfirm,
  }: {
    entry: { title: string; content: string; tags: string[]; entry_date: string };
    saving?: boolean;
    oncancel: () => void;
    onconfirm: () => void;
  } = $props();

  let newTag = $state("");

  function addTag() {
    const t = newTag.trim().toLowerCase();
    if (t && !entry.tags.includes(t)) entry.tags = [...entry.tags, t];
    newTag = "";
  }

  function removeTag(t: string) {
    entry.tags = entry.tags.filter((x) => x !== t);
  }

  function handleKey(e: KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    }
  }
</script>

<div class="modal-backdrop">
  <div class="modal">
    <h2>Eintrag bestätigen</h2>
    <label>
      Datum
      <input type="date" bind:value={entry.entry_date} />
    </label>
    <label>
      Titel
      <input bind:value={entry.title} maxlength="200" />
    </label>
    <label>
      Text
      <textarea bind:value={entry.content} rows="10"></textarea>
    </label>
    <div class="tags">
      {#each entry.tags as t (t)}
        <TagChip name={t} onremove={() => removeTag(t)} />
      {/each}
      <input
        bind:value={newTag}
        onkeydown={handleKey}
        placeholder="+ Tag"
        class="tag-input"
      />
    </div>
    <footer>
      <button type="button" onclick={oncancel} disabled={saving}>Zurück zum Chat</button>
      <button type="button" onclick={onconfirm} disabled={saving} class="primary">
        {#if saving}
          <Spinner label="Speichert Eintrag" /> <span>Speichere…</span>
        {:else}
          So speichern
        {/if}
      </button>
    </footer>
  </div>
</div>

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: grid;
    place-items: center;
    z-index: 10;
  }
  .modal {
    background: var(--bg);
    padding: 1.5rem;
    border-radius: var(--radius);
    width: min(600px, 90vw);
    max-height: 90vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .modal label { display: flex; flex-direction: column; gap: 0.25rem; }
  .tags { display: flex; flex-wrap: wrap; align-items: center; }
  .tag-input { width: 8rem; }
  footer { display: flex; gap: 0.5rem; justify-content: flex-end; align-items: center; flex-wrap: wrap; }
  footer .primary {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
  }
  footer button:disabled { opacity: 0.7; cursor: progress; }
  footer button { flex: 1 1 auto; min-width: 10rem; }
  @media (max-width: 500px) {
    footer button { flex: 1 1 100%; }
  }
</style>
