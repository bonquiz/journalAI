<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { Recorder, transcribe } from "$lib/audio";
  import EntryCard from "$lib/components/EntryCard.svelte";
  import SearchResultCard from "$lib/components/SearchResultCard.svelte";
  import SearchToggle from "$lib/components/SearchToggle.svelte";
  import { searchStore } from "$lib/stores/search.svelte";
  import { mergePage, hasMore } from "$lib/entries-pagination";

  type Item = { id: string; title: string; entry_date: string; content: string; tags: string[] };

  const PAGE_SIZE = 50;

  let allTags = $state<string[]>([]);
  let activeTags = $state<Set<string>>(new Set());
  let q = $state("");
  let items = $state<Item[]>([]);
  let total = $state(0);
  let loading = $state(false);

  let recording = $state(false);
  let transcribing = $state(false);
  let recorder: Recorder | null = null;
  let micError: string | null = $state(null);

  async function fetchPage(offset: number): Promise<{ items: Item[]; total: number }> {
    const tags = Array.from(activeTags).join(",");
    return await api<{ items: Item[]; total: number }>(
      `/api/entries?tags=${encodeURIComponent(tags)}&q=${encodeURIComponent(q)}`
      + `&offset=${offset}&limit=${PAGE_SIZE}`,
    );
  }

  async function loadFirstPage() {
    loading = true;
    try {
      const data = await fetchPage(0);
      items = data.items;
      total = data.total;
    } finally {
      loading = false;
    }
  }

  async function loadMore() {
    if (loading) return;
    loading = true;
    try {
      const data = await fetchPage(items.length);
      items = mergePage(items, data.items);
      total = data.total;
    } finally {
      loading = false;
    }
  }

  function toggle(t: string) {
    if (activeTags.has(t)) activeTags.delete(t);
    else activeTags.add(t);
    activeTags = new Set(activeTags);
    loadFirstPage();
  }

  function onKeywordSubmit(e: SubmitEvent) {
    e.preventDefault();
    loadFirstPage();
  }

  async function runSemanticSearch() {
    const query = searchStore.query.trim();
    if (!query) return;
    await searchStore.runSearch(query);
  }

  function onSemanticKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      runSemanticSearch();
    }
  }

  async function toggleRecording() {
    micError = null;
    if (recording) {
      recording = false;
      transcribing = true;
      try {
        const blob = await recorder!.stop();
        const text = await transcribe(blob);
        searchStore.setQuery(text);
        await searchStore.runSearch(text);
      } catch {
        micError = "Transkription fehlgeschlagen.";
      } finally {
        transcribing = false;
        recorder = null;
      }
      return;
    }
    try {
      recorder = new Recorder();
      await recorder.start();
      recording = true;
    } catch {
      micError = "Mikrofon nicht zugänglich.";
      recorder = null;
    }
  }

  onMount(async () => {
    allTags = await api<string[]>("/api/tags");
    await loadFirstPage();
  });
</script>

<h1>Einträge</h1>

<div class="mode-row">
  <SearchToggle value={searchStore.mode} onChange={(v) => searchStore.setMode(v)} />
</div>

{#if searchStore.mode === "semantic"}
  <div class="search-row">
    <input
      type="text"
      bind:value={searchStore.query}
      placeholder="Frag in ganzen Sätzen …"
      onkeydown={onSemanticKeydown}
    />
    <button
      type="button"
      onclick={toggleRecording}
      disabled={transcribing}
      aria-pressed={recording}
      aria-label={recording ? "Aufnahme beenden" : "Per Sprache suchen"}
      class:recording
    >
      {#if transcribing}
        …
      {:else if recording}
        ⏹
      {:else}
        🎤
      {/if}
    </button>
    <button
      type="button"
      onclick={runSemanticSearch}
      disabled={searchStore.loading || !searchStore.query.trim()}
    >
      {searchStore.loading ? "…" : "Suchen"}
    </button>
  </div>
  {#if micError}<p class="error">{micError}</p>{/if}
{:else}
  <form onsubmit={onKeywordSubmit}>
    <input bind:value={q} placeholder="Suche…" />
    <button type="submit">Suchen</button>
  </form>
{/if}

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

{#if searchStore.mode === "semantic"}
  {#if searchStore.error}
    <p class="error">{searchStore.error}</p>
  {:else if searchStore.lastResponse?.status === "not_configured"}
    <div class="banner warn">
      Semantische Suche ist nicht konfiguriert. <a href="/settings">Einstellungen öffnen</a>
    </div>
  {:else if searchStore.lastResponse?.status === "indexing"}
    <div class="banner info">
      Index wird gebaut … {searchStore.lastResponse.progress?.embedded ?? 0}
      von {searchStore.lastResponse.progress?.total ?? 0}
    </div>
  {:else if searchStore.lastResponse?.status === "error"}
    <div class="banner warn">
      Suchindex enthält beschädigte Einträge. <a href="/settings">Neu indexieren</a> empfohlen.
    </div>
  {:else if searchStore.results}
    <div class="search-results">
      {#if searchStore.results.length === 0}
        <p class="muted">Keine Treffer.</p>
      {:else}
        {#each searchStore.results as r (r.entry_id)}
          <SearchResultCard result={r} />
        {/each}
      {/if}
    </div>
  {/if}
{:else}
  {#if loading && items.length === 0}<p>Lade…</p>{/if}
  <div class="list">
    {#each items as e (e.id)}
      <EntryCard {e} />
    {/each}
    {#if !loading && items.length === 0}
      <p class="muted">Keine Einträge.</p>
    {/if}
  </div>
  {#if hasMore(items.length, total)}
    <div class="load-more">
      <button type="button" onclick={loadMore} disabled={loading}>
        {loading ? "Lade…" : `Mehr laden (${items.length}/${total})`}
      </button>
    </div>
  {/if}
{/if}

<style>
  .mode-row { margin: 1rem 0 0.5rem; }
  form { display: flex; gap: 0.5rem; margin: 0.5rem 0 1rem; flex-wrap: wrap; }
  form input { flex: 1 1 12rem; min-width: 0; }
  form button { flex: 0 0 auto; }
  .search-row {
    display: flex;
    gap: 0.5rem;
    margin: 0.5rem 0 1rem;
    flex-wrap: wrap;
    align-items: stretch;
  }
  .search-row input {
    flex: 1 1 12rem;
    min-width: 0;
  }
  .search-row button { flex: 0 0 auto; }
  .search-row button.recording { background: #c33; color: #fff; }
  .search-results { display: flex; flex-direction: column; gap: 0.75rem; }
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
  .banner { padding: 0.75rem 1rem; border-radius: 0.375rem; margin-bottom: 0.75rem; }
  .banner.warn { background: #fef3c7; color: #92400e; }
  .banner.info { background: #dbeafe; color: #1e40af; }
  .banner a { color: inherit; text-decoration: underline; }
  .error { color: #b91c1c; }
  .load-more { display: flex; justify-content: center; margin: 1rem 0 2rem; }
  .load-more button { min-height: 44px; padding: 0.6rem 1.25rem; }
</style>
