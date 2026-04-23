<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  import Spinner from "./Spinner.svelte";
  import { api } from "$lib/api";
  import { clearCurrent, setCurrent, stopAll } from "$lib/stores/playback";
  import { synthesize } from "$lib/tts";

  const { text }: { text: string } = $props();
  const instanceId = crypto.randomUUID();

  let audio: HTMLAudioElement | null = $state(null);
  let loading = $state(false);
  let playing = $state(false);
  let currentTime = $state(0);
  let duration = $state(0);
  let volume = $state(1);
  let speed = $state(1.0);

  function fmt(seconds: number): string {
    if (!isFinite(seconds) || seconds < 0) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, "0")}`;
  }

  async function loadAudio(): Promise<HTMLAudioElement | null> {
    loading = true;
    try {
      const result = await synthesize(text);
      if (!result) return null;
      const el = new Audio(result.url);
      el.preload = "metadata";
      el.playbackRate = speed;
      el.volume = volume;
      el.addEventListener("loadedmetadata", () => { duration = el.duration; });
      el.addEventListener("timeupdate", () => { currentTime = el.currentTime; });
      el.addEventListener("ended", () => { playing = false; currentTime = 0; });
      el.addEventListener("pause", () => { playing = false; });
      audio = el;
      return el;
    } finally {
      loading = false;
    }
  }

  async function togglePlay() {
    if (loading) return;
    if (!audio) {
      const el = await loadAudio();
      if (!el) return;
      stopAll();
      setCurrent(instanceId, el);
      await el.play();
      playing = true;
      return;
    }
    if (playing) {
      audio.pause();
    } else {
      stopAll();
      setCurrent(instanceId, audio);
      await audio.play();
      playing = true;
    }
  }

  function onSeek(e: Event) {
    const t = Number((e.target as HTMLInputElement).value);
    if (audio && isFinite(t)) audio.currentTime = t;
  }

  function onVolume(e: Event) {
    const v = Number((e.target as HTMLInputElement).value);
    volume = v;
    if (audio) audio.volume = v;
  }

  function onSpeed(e: Event) {
    const s = Number((e.target as HTMLInputElement).value);
    speed = s;
    if (audio) audio.playbackRate = s;
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === " ") { e.preventDefault(); togglePlay(); }
    else if (e.key === "ArrowLeft" && audio) { audio.currentTime = Math.max(0, audio.currentTime - 5); }
    else if (e.key === "ArrowRight" && audio) { audio.currentTime = Math.min(duration, audio.currentTime + 5); }
  }

  onMount(async () => {
    try {
      const s = await api<{ tts_speed: number | null }>("/api/settings");
      if (s.tts_speed) speed = s.tts_speed;
    } catch {
      /* leave default 1.0 */
    }
  });

  onDestroy(() => {
    if (audio) {
      audio.pause();
      audio.src = "";
      audio = null;
    }
    clearCurrent(instanceId);
  });
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<section class="player" aria-label="Audio-Wiedergabe" onkeydown={onKey}>
  <button
    type="button"
    class="play"
    onclick={togglePlay}
    disabled={loading}
    aria-label={playing ? "Pausieren" : "Vorlesen"}
  >
    {#if loading}
      <Spinner size={20} label="Lade Audio" />
    {:else if playing}
      ⏸
    {:else}
      ▶
    {/if}
  </button>

  <input
    class="progress"
    type="range"
    min="0"
    max={duration || 0}
    step="0.1"
    value={currentTime}
    oninput={onSeek}
    disabled={!audio}
    aria-label="Fortschritt"
  />

  <span class="time">{fmt(currentTime)} / {fmt(duration)}</span>

  <div class="controls-row">
    <label class="vol">
      <span aria-hidden="true">🔊</span>
      <input
        type="range" min="0" max="1" step="0.01"
        value={volume}
        oninput={onVolume}
        aria-label="Lautstärke"
      />
    </label>
    <label class="speed">
      <span>Tempo</span>
      <input
        type="range" min="0.5" max="2" step="0.05"
        value={speed}
        oninput={onSpeed}
        aria-label="Wiedergabegeschwindigkeit"
      />
      <span class="speed-val">{speed.toFixed(2)}×</span>
    </label>
  </div>
</section>

<style>
  .player {
    display: grid;
    grid-template-columns: auto 1fr auto;
    grid-template-areas:
      "play progress time"
      "controls controls controls";
    gap: 0.75rem 0.75rem;
    align-items: center;
    padding: 0.75rem 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: #fafbfc;
    margin: 0.75rem 0 1rem;
  }
  .play {
    grid-area: play;
    width: 48px; height: 48px; min-height: 48px;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 1.2em;
  }
  .progress {
    grid-area: progress;
    width: 100%;
    min-height: 24px;
  }
  .time {
    grid-area: time;
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    font-size: 0.9em;
  }
  .controls-row {
    grid-area: controls;
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    align-items: center;
  }
  .vol, .speed {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex: 1 1 auto;
    min-width: 10rem;
  }
  .speed .speed-val {
    font-variant-numeric: tabular-nums;
    color: var(--muted);
    font-size: 0.85em;
  }

  input[type="range"] {
    flex: 1;
    min-height: 24px;
    padding: 0.5rem 0;
    background: transparent;
    -webkit-appearance: none;
    appearance: none;
  }
  input[type="range"]::-webkit-slider-runnable-track {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
  }
  input[type="range"]::-moz-range-track {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    border: none;
  }
  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    margin-top: -6px;
    border: none;
  }
  input[type="range"]::-moz-range-thumb {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
    border: none;
  }
  input[type="range"]:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  @media (max-width: 600px) {
    .player {
      grid-template-columns: auto 1fr;
      grid-template-areas:
        "play progress"
        "time time"
        "controls controls";
      padding: 0.6rem 0.75rem;
    }
    .time { text-align: right; }
    .vol, .speed { flex: 1 1 100%; min-width: 0; }
  }
</style>
