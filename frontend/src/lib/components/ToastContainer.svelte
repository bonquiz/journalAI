<script lang="ts">
  import { fade, fly } from "svelte/transition";
  import { toast } from "$lib/stores/toast";
</script>

<div class="toast-container" aria-live="polite">
  {#each $toast as t (t.id)}
    <div
      class="toast toast-{t.level}"
      role={t.level === "error" ? "alert" : "status"}
      in:fly={{ y: -10, duration: 150 }}
      out:fade={{ duration: 120 }}
    >
      <span class="msg">{t.message}</span>
      <button type="button" aria-label="Meldung schließen"
              onclick={() => toast.dismiss(t.id)}>×</button>
    </div>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    top: 1rem;
    right: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 1000;
    max-width: min(420px, calc(100vw - 2rem));
    pointer-events: none;
  }
  .toast-container .toast {
    pointer-events: auto;
  }
  .toast {
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.65rem 0.85rem;
    border-radius: var(--radius);
    background: #fff;
    border: 1px solid var(--border);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.1);
  }
  .toast .msg { flex: 1; font-size: 0.95em; }
  .toast button {
    background: transparent;
    color: var(--muted);
    border: none;
    padding: 0 0.25rem;
    font-size: 1.2em;
    line-height: 1;
    min-height: 32px;
    cursor: pointer;
  }
  .toast-info { border-left: 3px solid var(--accent); }
  .toast-success { border-left: 3px solid #2f7d32; }
  .toast-error { border-left: 3px solid #b22; }

  @media (max-width: 600px) {
    .toast-container {
      top: 0.5rem;
      left: 0.5rem;
      right: 0.5rem;
      max-width: none;
    }
  }
</style>
