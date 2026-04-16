<script lang="ts">
  import { Recorder, transcribe } from "$lib/audio";

  const { oninsert }: { oninsert: (text: string) => void } = $props();

  let rec: Recorder | null = null;
  let active = $state(false);
  let loading = $state(false);
  let error: string | null = $state(null);

  async function toggle() {
    error = null;
    if (!active) {
      try {
        rec = new Recorder();
        await rec.start();
        active = true;
      } catch (e) {
        error = "Mikrofon nicht zugänglich.";
        rec = null;
      }
    } else {
      active = false;
      loading = true;
      try {
        const blob = await rec!.stop();
        const text = await transcribe(blob);
        oninsert(text);
      } catch {
        error = "Transkription fehlgeschlagen.";
      } finally {
        loading = false;
        rec = null;
      }
    }
  }
</script>

<button
  type="button"
  onclick={toggle}
  aria-pressed={active}
  aria-label={active ? "Aufnahme beenden" : "Aufnahme starten"}
  disabled={loading}
  class:recording={active}
>
  {#if loading}…{:else if active}■ Stopp{:else}● Mic{/if}
</button>
{#if error}<span class="err">{error}</span>{/if}

<style>
  button.recording { background: #c33; }
  .err { color: #b22; margin-left: 0.5rem; font-size: 0.9em; }
</style>
