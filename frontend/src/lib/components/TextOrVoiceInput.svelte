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
  <textarea bind:value {placeholder} onkeydown={handleKey} rows="4"></textarea>
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
  textarea { width: 100%; resize: vertical; font-family: inherit; }
  .controls { display: flex; gap: 0.5rem; }
</style>
