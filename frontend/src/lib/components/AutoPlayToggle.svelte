<script lang="ts">
  let {
    value = $bindable(false),
    label = "Auto-Vorlesen",
    help = "Assistenten-Antworten werden nach dem Streaming automatisch vorgelesen. Gilt nur für diese Eintragssession.",
  }: {
    value?: boolean;
    label?: string;
    help?: string;
  } = $props();

  function toggle() {
    value = !value;
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      toggle();
    }
  }
</script>

<div class="row">
  <span class="label">{label}</span>
  <button
    type="button"
    class="switch"
    role="switch"
    aria-checked={value}
    aria-label={label}
    onclick={toggle}
    onkeydown={onKey}
  >
    <span class="thumb"></span>
  </button>
  <span class="info" title={help} aria-label={help}>ⓘ</span>
</div>

<style>
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0.5rem 0 1rem;
  }
  .label { font-size: 0.95em; }
  .switch {
    position: relative;
    width: 44px;
    height: 24px;
    background: var(--border);
    border: none;
    border-radius: 12px;
    padding: 0;
    cursor: pointer;
    transition: background 0.15s ease;
    min-height: 24px;
  }
  .switch[aria-checked="true"] { background: var(--accent); }
  .thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 20px;
    height: 20px;
    background: #fff;
    border-radius: 50%;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
    transition: transform 0.15s ease;
  }
  .switch[aria-checked="true"] .thumb { transform: translateX(20px); }
  .info {
    color: var(--muted);
    cursor: help;
    font-size: 1em;
    user-select: none;
  }
</style>
