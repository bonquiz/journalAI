<script lang="ts">
  import type { RerankedResult } from "$lib/search";

  interface Props {
    result: RerankedResult;
  }

  let { result }: Props = $props();
</script>

<a class="card" href={`/entries/${result.entry_id}`}>
  <div class="header">
    <h3>{result.title}</h3>
    <span class="score" aria-label="Relevanz">{Math.round(result.score)}</span>
  </div>
  <p class="excerpt">{result.excerpt}</p>
  {#if result.reason}
    <p class="reason" data-testid="reason-line">{result.reason}</p>
  {/if}
</a>

<style>
  .card {
    display: block;
    padding: 1rem;
    border: 1px solid var(--border, #ddd);
    border-radius: 0.5rem;
    color: inherit;
    text-decoration: none;
    background: var(--bg, white);
  }
  .card:hover {
    background: var(--bg-subtle, #f7f7f7);
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }
  h3 {
    margin: 0;
    font-size: 1rem;
  }
  .score {
    font-size: 0.75rem;
    padding: 0.15rem 0.4rem;
    background: var(--accent-soft, #dbeafe);
    color: var(--accent, #2563eb);
    border-radius: 999px;
  }
  .excerpt {
    margin: 0.5rem 0 0.25rem;
    color: var(--muted, #555);
    font-size: 0.9rem;
  }
  .reason {
    margin: 0.25rem 0 0;
    color: var(--muted, #888);
    font-size: 0.8rem;
    font-style: italic;
  }
</style>
