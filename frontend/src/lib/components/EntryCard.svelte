<script lang="ts">
  const { e }: {
    e: { id: string; title: string; entry_date: string; content: string; tags: string[] };
  } = $props();

  const getExcerpt = (content: string) => content.slice(0, 150) + (content.length > 150 ? "…" : "");
</script>

<a href={`/entries/${e.id}`} class="card">
  <time>{e.entry_date}</time>
  <h3>{e.title}</h3>
  <p>{getExcerpt(e.content)}</p>
  <div class="tags">
    {#each e.tags as t (t)}<span class="chip">{t}</span>{/each}
  </div>
</a>

<style>
  .card {
    display: block;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin: 0.5rem 0;
    text-decoration: none;
    color: inherit;
    background: #fff;
  }
  .card:hover { border-color: var(--accent); }
  .card time { font-size: 0.85em; color: var(--muted); }
  .card h3 { margin: 0.25rem 0; }
  .card p { margin: 0 0 0.5rem; color: var(--muted); }
  .chip {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    margin: 0.1rem;
    background: #e8ecf1;
    border-radius: 999px;
    font-size: 0.8em;
  }
</style>
