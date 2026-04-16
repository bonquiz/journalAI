<script lang="ts">
  import { onMount } from "svelte";
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { marked } from "marked";

  import { api } from "$lib/api";
  import { formatLong } from "$lib/format";
  import TagChip from "$lib/components/TagChip.svelte";

  marked.setOptions({ gfm: true, breaks: true });

  type EntryDetail = {
    id: string;
    title: string;
    content: string;
    entry_date: string;
    tags: string[];
    created_at: string;
    updated_at: string;
    raw_transcript?: string | null;
    chat_history?: unknown;
  };

  let entry = $state<EntryDetail | null>(null);
  let editing = $state(false);
  let draft = $state<EntryDetail | null>(null);
  let newTag = $state("");
  let error: string | null = $state(null);

  onMount(async () => {
    try {
      entry = await api<EntryDetail>(`/api/entries/${$page.params.id}`);
    } catch {
      error = "Eintrag konnte nicht geladen werden.";
    }
  });

  function startEdit() {
    if (!entry) return;
    draft = JSON.parse(JSON.stringify(entry));
    editing = true;
  }

  function cancelEdit() {
    editing = false;
    draft = null;
    newTag = "";
  }

  function addTag() {
    if (!draft) return;
    const t = newTag.trim().toLowerCase();
    if (t && !draft.tags.includes(t)) draft.tags = [...draft.tags, t];
    newTag = "";
  }

  function removeTag(t: string) {
    if (!draft) return;
    draft.tags = draft.tags.filter((x) => x !== t);
  }

  function handleTagKey(e: KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      addTag();
    }
  }

  async function save(e: SubmitEvent) {
    e.preventDefault();
    if (!draft || !entry) return;
    try {
      entry = await api<EntryDetail>(`/api/entries/${entry.id}`, {
        method: "PUT",
        body: {
          title: draft.title,
          content: draft.content,
          tags: draft.tags,
          entry_date: draft.entry_date,
        },
      });
      editing = false;
      draft = null;
    } catch {
      error = "Speichern fehlgeschlagen.";
    }
  }

  async function remove() {
    if (!entry) return;
    if (!confirm(`"${entry.title}" wirklich löschen?`)) return;
    try {
      await api(`/api/entries/${entry.id}`, { method: "DELETE" });
      goto("/entries");
    } catch {
      error = "Löschen fehlgeschlagen.";
    }
  }
</script>

{#if error}<p class="err">{error}</p>{/if}

{#if entry && !editing}
  <article class="detail">
    <time datetime={entry.entry_date}>{formatLong(entry.entry_date)}</time>
    <h1>{entry.title}</h1>
    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
    <div class="content markdown">{@html marked.parse(entry.content) as string}</div>
    <div class="tags">
      {#each entry.tags as t (t)}<TagChip name={t} />{/each}
    </div>
    <footer>
      <button type="button" onclick={startEdit}>Bearbeiten</button>
      <button type="button" onclick={remove} class="danger">Löschen</button>
      <a href="/entries">Zurück</a>
    </footer>
  </article>
{:else if editing && draft}
  <form onsubmit={save} class="edit-form">
    <label>
      Datum
      <input type="date" bind:value={draft.entry_date} required />
    </label>
    <label>
      Titel
      <input bind:value={draft.title} required maxlength="200" />
    </label>
    <label>
      Text
      <textarea rows="15" bind:value={draft.content} required></textarea>
    </label>
    <div class="tags">
      {#each draft.tags as t (t)}
        <TagChip name={t} onremove={() => removeTag(t)} />
      {/each}
      <input
        bind:value={newTag}
        onkeydown={handleTagKey}
        placeholder="+ Tag"
        class="tag-input"
      />
    </div>
    <footer>
      <button type="submit">Speichern</button>
      <button type="button" onclick={cancelEdit}>Abbrechen</button>
    </footer>
  </form>
{/if}

<style>
  .detail time { color: var(--muted); }
  .content {
    line-height: 1.6;
    background: #f5f7fa;
    padding: 1rem;
    border-radius: var(--radius);
  }
  .content.markdown :global(h1),
  .content.markdown :global(h2),
  .content.markdown :global(h3) { margin: 0.8rem 0 0.4rem; }
  .content.markdown :global(p) { margin: 0.6rem 0; }
  .content.markdown :global(ul),
  .content.markdown :global(ol) { margin: 0.5rem 0; padding-left: 1.5rem; }
  .content.markdown :global(strong) { font-weight: 600; }
  .content.markdown :global(blockquote) {
    border-left: 3px solid var(--border);
    margin: 0.5rem 0;
    padding-left: 1rem;
    color: var(--muted);
  }
  .tags { display: flex; flex-wrap: wrap; align-items: center; margin: 0.75rem 0; }
  .tag-input { width: 8rem; }
  .edit-form { display: flex; flex-direction: column; gap: 0.75rem; }
  .edit-form label { display: flex; flex-direction: column; gap: 0.25rem; }
  footer { display: flex; gap: 0.5rem; margin-top: 1rem; }
  .danger { background: #c33; }
  .err { color: #b22; }
</style>
