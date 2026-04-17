<script lang="ts">
  interface Mismatch { old_model: string; new_model: string; affected_entries: number; }
  interface Props {
    open: boolean;
    mismatch: Mismatch;
    onRevert: () => void;
    onReindex: () => void;
    onLater: () => void;
  }
  let { open, mismatch, onRevert, onReindex, onLater }: Props = $props();
</script>

{#if open}
  <div class="backdrop" role="presentation">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="mm-title">
      <h2 id="mm-title">Embedding-Modell geändert</h2>
      <p>
        Deine bisherigen <strong>{mismatch.affected_entries}</strong> Einträge wurden mit
        <code>{mismatch.old_model}</code> indexiert. Du hast jetzt
        <code>{mismatch.new_model}</code> gewählt. Die Modelle sind untereinander nicht
        kompatibel — die semantische Suche funktioniert nur auf Einträgen im aktuellen Modell.
      </p>
      <p>Was möchtest du tun?</p>
      <div class="actions">
        <button type="button" onclick={onRevert}>Zurück zum alten Modell</button>
        <button type="button" class="primary" onclick={onReindex}>Neu indexieren</button>
        <button type="button" class="subtle" onclick={onLater}>Später entscheiden</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.35);
    display: grid; place-items: center; z-index: 1000;
  }
  .dialog {
    background: white; padding: 1.5rem; border-radius: 0.5rem;
    max-width: 32rem; width: calc(100% - 2rem);
    box-shadow: 0 10px 30px rgba(0,0,0,0.2);
  }
  h2 { margin-top: 0; }
  .actions { display: flex; gap: 0.5rem; justify-content: flex-end; flex-wrap: wrap; margin-top: 1rem; }
  button { min-height: 44px; padding: 0.5rem 1rem; border-radius: 0.375rem; border: 1px solid var(--border, #ccc); background: white; cursor: pointer; }
  button.primary { background: var(--accent, #2563eb); color: white; border-color: transparent; }
  button.subtle { background: transparent; border-color: transparent; color: var(--muted, #666); }
</style>
