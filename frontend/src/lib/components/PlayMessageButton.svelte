<script lang="ts">
  import { onDestroy } from "svelte";

  import Spinner from "./Spinner.svelte";
  import { clearCurrent, currentPlayback, setCurrent, stopAll } from "$lib/stores/playback";
  import { synthesize } from "$lib/tts";

  const { text, autoplay = false }:
    { text: string; autoplay?: boolean } = $props();

  const instanceId = crypto.randomUUID();

  let audio: HTMLAudioElement | null = $state(null);
  let loading = $state(false);
  let playing = $state(false);

  $effect(() => {
    if ($currentPlayback?.id !== instanceId && playing) {
      playing = false;
    }
  });

  async function ensureAudio(): Promise<HTMLAudioElement | null> {
    if (audio) return audio;
    loading = true;
    try {
      const result = await synthesize(text);
      if (!result) return null;
      const el = new Audio(result.url);
      el.preload = "metadata";
      el.addEventListener("ended", () => { playing = false; });
      el.addEventListener("pause", () => {
        if ($currentPlayback?.element === el) playing = false;
      });
      audio = el;
      return el;
    } finally {
      loading = false;
    }
  }

  async function toggle() {
    if (loading) return;

    if (playing && audio) {
      audio.pause();
      playing = false;
      return;
    }

    if (audio && !playing) {
      stopAll();
      setCurrent(instanceId, audio);
      await audio.play();
      playing = true;
      return;
    }

    const el = await ensureAudio();
    if (!el) return;
    stopAll();
    setCurrent(instanceId, el);
    await el.play();
    playing = true;
  }

  onDestroy(() => {
    if (audio) {
      audio.pause();
      audio.src = "";
      audio = null;
    }
    clearCurrent(instanceId);
  });

  // Auto-play support: when the `autoplay` prop becomes true, fire toggle() once.
  let autoplayFired = false;
  $effect(() => {
    if (autoplay && !autoplayFired && text.trim().length > 0) {
      autoplayFired = true;
      toggle();
    }
  });
</script>

<button
  type="button"
  class="play-btn"
  class:playing
  onclick={toggle}
  disabled={loading}
  aria-label={playing ? "Pausieren" : "Nachricht vorlesen"}
  aria-pressed={playing}
>
  {#if loading}
    <Spinner size={14} label="Lade Audio" />
  {:else if playing}
    ⏸
  {:else}
    🔊
  {/if}
</button>

<style>
  .play-btn {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 999px;
    width: 32px;
    height: 32px;
    min-height: 32px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }
  .play-btn:hover { border-color: var(--accent); color: var(--accent); }
  .play-btn.playing {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
  }
  .play-btn:disabled { cursor: progress; opacity: 0.7; }
</style>
