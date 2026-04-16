<script lang="ts">
  import { marked } from "marked";

  let {
    role,
    content,
    children,
  }: {
    role: string;
    content: string;
    children?: import("svelte").Snippet;
  } = $props();

  marked.setOptions({ gfm: true, breaks: true });

  const rendered = $derived(
    role === "assistant" ? (marked.parse(content) as string) : content,
  );
</script>

<article class="msg {role}">
  <header>
    <span>{role === "user" ? "Du" : "Assistent"}</span>
    {#if children}
      <span class="actions">{@render children()}</span>
    {/if}
  </header>
  {#if role === "assistant"}
    <!-- eslint-disable-next-line svelte/no-at-html-tags -->
    <div class="body markdown">{@html rendered}</div>
  {:else}
    <div class="body plain">{content}</div>
  {/if}
</article>

<style>
  .msg { margin: 0.75rem 0; padding: 0.75rem 1rem; border-radius: var(--radius); }
  .msg.user { background: #eef2f6; }
  .msg.assistant { background: #f5f7fa; }
  .msg header {
  font-weight: 600;
  font-size: 0.85em;
  color: var(--muted);
  margin-bottom: 0.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}
.msg header .actions { display: inline-flex; }
  .body.plain { white-space: pre-wrap; }
  .body.markdown :global(h1),
  .body.markdown :global(h2),
  .body.markdown :global(h3) { margin: 0.6rem 0 0.3rem; }
  .body.markdown :global(p) { margin: 0.5rem 0; }
  .body.markdown :global(ul),
  .body.markdown :global(ol) { margin: 0.4rem 0; padding-left: 1.4rem; }
  .body.markdown :global(li) { margin: 0.15rem 0; }
  .body.markdown :global(code) { background: #e8ecf1; padding: 0.05rem 0.3rem; border-radius: 3px; font-size: 0.9em; }
  .body.markdown :global(blockquote) { border-left: 3px solid var(--border); margin: 0.4rem 0; padding-left: 0.75rem; color: var(--muted); }
  .body.markdown :global(strong) { font-weight: 600; }
</style>
