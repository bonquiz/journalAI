<script lang="ts">
  type Mode = "keyword" | "semantic";
  interface Props { value: Mode; onChange: (v: Mode) => void; }
  let { value, onChange }: Props = $props();

  function toggle() {
    onChange(value === "keyword" ? "semantic" : "keyword");
  }
</script>

<button
  type="button"
  role="switch"
  aria-checked={value === "semantic"}
  aria-label="Semantische Suche umschalten"
  class="search-toggle"
  data-mode={value}
  onclick={toggle}
>
  <span class="label" class:active={value === "keyword"}>Stichwort</span>
  <span class="label" class:active={value === "semantic"}>Semantisch</span>
</button>

<style>
  .search-toggle {
    display: inline-flex;
    gap: 0.25rem;
    padding: 0.25rem;
    border: 1px solid var(--border, #ccc);
    border-radius: 999px;
    background: var(--bg-subtle, #f4f4f4);
    min-height: 44px;
    cursor: pointer;
  }
  .label {
    padding: 0.4rem 0.9rem;
    border-radius: 999px;
    font-size: 0.875rem;
    color: var(--muted, #666);
  }
  .label.active {
    background: var(--accent, #2563eb);
    color: white;
  }
</style>
