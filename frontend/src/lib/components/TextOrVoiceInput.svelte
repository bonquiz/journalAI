<script lang="ts">
  import RecordButton from "./RecordButton.svelte";

  let {
    value = $bindable(""),
    placeholder = "",
    onsubmit,
  }: {
    value?: string;
    placeholder?: string;
    onsubmit?: () => void;
  } = $props();

  function insert(t: string) {
    value = value ? value + "\n" + t : t;
  }

  function handleKey(e: KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      onsubmit?.();
    }
  }
</script>

<div class="tovi">
  <textarea bind:value {placeholder} onkeydown={handleKey} rows="8"></textarea>
  <div class="controls">
    <RecordButton oninsert={insert} />
    {#if onsubmit}
      <button type="button" onclick={onsubmit} disabled={!value.trim()}>
        Senden
      </button>
    {/if}
  </div>
</div>

<style>
  .tovi { display: flex; flex-direction: column; gap: 0.5rem; }
  textarea {
    width: 100%;
    min-height: 12rem;
    resize: vertical;
    font-family: inherit;
    /* field-sizing grows the box with content on browsers that support it,
       which replaces the missing drag-handle on mobile. */
    field-sizing: content;
  }
  .controls { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .controls :global(button) { flex: 1 1 auto; min-width: 8rem; }
</style>
