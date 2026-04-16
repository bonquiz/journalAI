<script lang="ts">
  import { api } from "$lib/api";
  import { session } from "$lib/stores/session";

  let showWarn = $derived(
    $session.authenticated && $session.idleSecondsLeft <= 60 && $session.idleSecondsLeft > 0,
  );

  function fmt(s: number): string {
    const m = Math.floor(s / 60);
    const r = s % 60;
    return `${m}:${r.toString().padStart(2, "0")}`;
  }

  async function heartbeat() {
    await api("/api/session/ping", { method: "POST" });
    // Activity-reset in store is fired by the button click event itself.
  }
</script>

{#if $session.authenticated}
  <span class="countdown" title="Automatische Abmeldung bei Inaktivität">
    {fmt($session.idleSecondsLeft)}
  </span>
{/if}

{#if showWarn}
  <div class="warn-modal">
    <p>In {$session.idleSecondsLeft} Sekunden wirst du abgemeldet.</p>
    <button type="button" onclick={heartbeat}>Aktiv bleiben</button>
  </div>
{/if}

<style>
  .countdown {
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    font-size: 0.9em;
  }
  .warn-modal {
    position: fixed;
    top: 1rem;
    right: 1rem;
    background: #fef3c7;
    border: 1px solid #f3b90d;
    padding: 1rem;
    border-radius: var(--radius);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    z-index: 20;
  }
  .warn-modal p { margin: 0 0 0.5rem; }
</style>
