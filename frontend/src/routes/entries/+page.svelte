<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import EntryCard from "$lib/components/EntryCard.svelte";

  type Item = { id: string; title: string; entry_date: string; content: string; tags: string[] };

  let allTags = $state<string[]>([]);
  let activeTags = $state<Set<string>>(new Set());
  let q = $state("");
  let items = $state<Item[]>([]);
  let loading = $state(false);

  async function load() {
    loading = true;
    try {
      const tags = Array.from(activeTags).join(",");
      const data = await api<{ items: Item[] }>(
        `/api/entries?tags=${encodeURIComponent(tags)}&q=${encodeURIComponent(q)}`,
      );
      items = data.items;
    } finally {
      loading = false;
    }
  }

  function toggle(t: string) {
    if (activeTags.has(t)) activeTags.delete(t);
    else activeTags.add(t);
    activeTags = new Set(activeTags);
    load();
  }

  function onSearch(e: SubmitEvent) {
    e.preventDefault();
    load();
  }

  onMount(async () => {
    allTags = await api<string[]>("/api/tags");
    await load();
  });
</script>

<h1>Einträge</h1>

<form onsubmit={onSearch}>
  <input bind:value={q} placeholder="Suche…" />
  <button type="submit">Suchen</button>
</form>

{#if allTags.length}
  <div class="tags">
    {#each allTags as t (t)}
      <button
        type="button"
        class="tag-btn"
        class:active={activeTags.has(t)}
        onclick={() => toggle(t)}
      >{t}</button>
    {/each}
  </div>
{/if}

{#if loading}<p>Lade…</p>{/if}

<div class="list">
  {#each items as e (e.id)}
    <EntryCard {e} />
  {/each}
  {#if !loading && items.length === 0}
    <p class="muted">Keine Einträge.</p>
  {/if}
</div>

<style>
  form { display: flex; gap: 0.5rem; margin: 1rem 0; flex-wrap: wrap; }
  form input { flex: 1 1 12rem; min-width: 0; }
  form button { flex: 0 0 auto; }
  .tags { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 1rem; }
  .tag-btn {
    background: #e8ecf1;
    color: var(--fg);
    font-size: 0.85em;
    padding: 0.35rem 0.7rem;
    min-height: 36px;
    border-radius: 999px;
  }
  .tag-btn.active { background: var(--accent); color: #fff; }
  .muted { color: var(--muted); font-style: italic; }
</style>
