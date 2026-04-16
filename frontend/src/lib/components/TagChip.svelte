<script lang="ts">
  const { name, onremove }: { name: string; onremove?: () => void } = $props();
</script>

<span class="chip">
  {name}
  {#if onremove}
    <button type="button" onclick={onremove} aria-label="remove tag">×</button>
  {/if}
</span>

<style>
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.2rem 0.6rem;
    background: #e8ecf1;
    border-radius: 999px;
    font-size: 0.85em;
    margin: 0.15rem;
  }
  .chip button {
    background: transparent;
    border: none;
    padding: 0;
    color: var(--muted);
    cursor: pointer;
    font-size: 1em;
    line-height: 1;
  }
</style>
