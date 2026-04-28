<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";
  import { getSearchStatus, reindexEmbeddings, type SearchStatus } from "$lib/search";
  import DataPortability from "$lib/components/DataPortability.svelte";
  import ModelMismatchDialog from "$lib/components/ModelMismatchDialog.svelte";
  import { envHint } from "$lib/settings-env-hint";

  type CoachPreset = { key: string; label: string; text: string };
  type SettingsOut = {
    stt_base_url: string | null; stt_api_key_masked: string | null; stt_model: string | null;
    chat_base_url: string | null; chat_api_key_masked: string | null; chat_model: string | null;
    embed_base_url: string | null; embed_api_key_masked: string | null; embed_model: string | null;
    tts_base_url: string | null; tts_api_key_masked: string | null; tts_model: string | null;
    coach_prompt: string | null;
    summary_prompt: string | null;
    coach_presets: CoachPreset[];
    default_coach_preset_key: string;
    tts_voice: string | null; tts_speed: number | null;
    totp_enabled: boolean;
    stt_resolved_base_url: string | null; stt_resolved_model: string | null;
    chat_resolved_base_url: string | null; chat_resolved_model: string | null;
    embed_resolved_base_url: string | null; embed_resolved_model: string | null;
    tts_resolved_base_url: string | null; tts_resolved_model: string | null;
  };

  type EmbeddingMismatch = { old_model: string; new_model: string; affected_entries: number };
  type SettingsPutResponse = SettingsOut & {
    warning?: string;
    embedding_mismatch?: EmbeddingMismatch;
  };

  let s = $state<SettingsOut | null>(null);
  let form = $state<Record<string, string | number | null>>({});
  let pwOld = $state("");
  let pwNew = $state("");
  let totpSetup = $state<{ secret: string; qr_png_base64: string } | null>(null);
  let totpCode = $state("");
  let msg: string | null = $state(null);

  function applyCoachPreset(preset: CoachPreset) {
    const current = (form.coach_prompt ?? s?.coach_prompt ?? "") as string;
    const isCustom =
      current.trim().length > 0 &&
      !s?.coach_presets.some((p) => p.text === current);
    if (isCustom && !confirm("Eigenen Coach-Prompt durch Vorlage ersetzen?")) return;
    form.coach_prompt = preset.text;
  }

  function clearCoachPrompt() {
    const current = (form.coach_prompt ?? s?.coach_prompt ?? "") as string;
    if (current.trim().length > 0 && !confirm("Textfeld leeren?")) return;
    form.coach_prompt = "";
  }

  function defaultCoachText(): string {
    const k = s?.default_coach_preset_key ?? "therapist";
    return s?.coach_presets.find((p) => p.key === k)?.text ?? "";
  }

  let embedStatus: SearchStatus | null = $state(null);
  let mismatch: EmbeddingMismatch | null = $state(null);

  async function load() {
    s = await api<SettingsOut>("/api/settings");
  }

  async function loadStatus() {
    try {
      embedStatus = await getSearchStatus();
    } catch {
      /* ignore */
    }
  }

  onMount(async () => {
    await load();
    await loadStatus();
  });

  async function saveEndpoints() {
    msg = null;
    const resp = await api<SettingsPutResponse>("/api/settings", { method: "PUT", body: form });
    form = {};
    if (resp && typeof resp === "object") {
      const { warning, embedding_mismatch, ...rest } = resp;
      s = rest as SettingsOut;
      if (warning === "embedding_model_mismatch" && embedding_mismatch) {
        mismatch = embedding_mismatch;
      }
    } else {
      await load();
    }
    await loadStatus();
    msg = "Einstellungen gespeichert.";
  }

  async function triggerReindex() {
    if (!confirm(`Alle ${embedStatus?.total ?? 0} Einträge werden neu indexiert. Fortfahren?`)) return;
    await reindexEmbeddings();
    await loadStatus();
  }

  async function changePw() {
    msg = null;
    try {
      await api("/api/settings/password", {
        method: "POST",
        body: { old_password: pwOld, new_password: pwNew },
      });
      msg = "Passwort geändert. Du wirst abgemeldet…";
      setTimeout(() => (window.location.href = "/login"), 1500);
    } catch {
      msg = "Passwortänderung fehlgeschlagen.";
    }
  }

  async function startTotp() {
    totpSetup = await api<{ secret: string; qr_png_base64: string }>(
      "/api/auth/totp/setup",
      { method: "POST" },
    );
  }

  async function confirmTotp() {
    try {
      await api("/api/auth/totp/confirm", { method: "POST", body: { code: totpCode } });
      totpSetup = null;
      totpCode = "";
      await load();
      msg = "TOTP aktiviert. Bitte neu anmelden.";
      setTimeout(() => (window.location.href = "/login"), 1500);
    } catch {
      msg = "TOTP-Code ungültig.";
    }
  }

  function voiceTooltip(baseUrl: string | null): string {
    const u = (baseUrl ?? "").toLowerCase();
    if (u.includes("openai.com")) return "z. B. alloy, echo, fable, onyx, nova, shimmer";
    if (u.includes("kokoro") || u.includes(":8880")) return "z. B. af_sarah, af_bella, am_adam";
    if (u.includes("openedai") || u.includes(":8000")) return "gemäß voice_to_speaker.yaml deines Servers";
    return "Laut Dokumentation deines TTS-Servers";
  }

  const caps = ["stt", "chat", "embed", "tts"] as const;
</script>

<h1>Einstellungen</h1>
{#if msg}<p class="msg">{msg}</p>{/if}

{#if s}
  <section class="card">
    <h2>Endpoints</h2>
    {#each caps as cap (cap)}
      <fieldset>
        <legend>{cap.toUpperCase()}</legend>
        <label>
          Base URL
          <input bind:value={form[`${cap}_base_url`]} placeholder={s[`${cap}_base_url`] ?? ""} />
          {#if envHint(form[`${cap}_base_url`] as string | null, s[`${cap}_resolved_base_url`])}
            <small class="env-hint">aus ENV: {envHint(form[`${cap}_base_url`] as string | null, s[`${cap}_resolved_base_url`])}</small>
          {/if}
        </label>
        <label>
          API Key
          <input type="password" bind:value={form[`${cap}_api_key`]}
                 placeholder={s[`${cap}_api_key_masked`] ?? "-"} />
        </label>
        <label>
          Model
          <input bind:value={form[`${cap}_model`]} placeholder={s[`${cap}_model`] ?? ""} />
          {#if envHint(form[`${cap}_model`] as string | null, s[`${cap}_resolved_model`])}
            <small class="env-hint">aus ENV: {envHint(form[`${cap}_model`] as string | null, s[`${cap}_resolved_model`])}</small>
          {/if}
        </label>
      </fieldset>
    {/each}
    <fieldset>
      <legend>TTS-Stimme & Tempo</legend>
      <label>
        Voice
        <input
          bind:value={form.tts_voice}
          placeholder={s.tts_voice ?? "alloy"}
          title={voiceTooltip(s.tts_base_url)}
        />
      </label>
      <label>
        Tempo
        <input
          type="range" min="0.5" max="2" step="0.05"
          bind:value={form.tts_speed}
          aria-label="Vorlese-Tempo"
        />
        <span class="muted">{(typeof form.tts_speed === "number" ? form.tts_speed : s.tts_speed ?? 1.0).toFixed(2)}×</span>
      </label>
    </fieldset>
    <fieldset class="prompt-section">
      <legend>Coach-Prompt (Reflexions-Dialog)</legend>
      <p class="muted">
        Der Coach begleitet dich beim Reflektieren — er strukturiert nichts und
        schreibt keinen Eintrag. Wähle eine Persona oder formuliere einen
        eigenen Prompt.
      </p>
      <div class="preset-buttons">
        {#each s.coach_presets as preset (preset.key)}
          <button type="button" onclick={() => applyCoachPreset(preset)}>
            {preset.label}
          </button>
        {/each}
        <button type="button" onclick={clearCoachPrompt}>Eigener Prompt</button>
      </div>
      <textarea
        bind:value={form.coach_prompt}
        rows="10"
        placeholder={s.coach_prompt ?? defaultCoachText()}
      ></textarea>
    </fieldset>

    <fieldset class="prompt-section">
      <legend>Zusammenfassungs-Prompt</legend>
      <p class="muted">
        Wenn du auf „Tagebucheintrag erstellen" klickst, baut dieses Modell aus
        eurem Dialog den fertigen Eintrag. Du kannst den Stil hier anpassen —
        die JSON-Struktur des Eintrags wird automatisch ergänzt.
      </p>
      <textarea
        bind:value={form.summary_prompt}
        rows="10"
        placeholder={s.summary_prompt ?? ""}
      ></textarea>
    </fieldset>

    <button type="button" onclick={saveEndpoints}>Speichern</button>
  </section>

  <section class="card embed-status">
    <h2>Index-Status</h2>
    {#if embedStatus}
      <p>
        {embedStatus.embedded} von {embedStatus.total} Einträgen indexiert
        (Modell: {embedStatus.current_model ?? "–"})
        {#if embedStatus.indexing} — <em>läuft gerade</em>{/if}
      </p>
      <button type="button" onclick={triggerReindex} disabled={embedStatus.indexing}>
        Jetzt neu indexieren
      </button>
    {:else}
      <p class="muted">Status wird geladen…</p>
    {/if}
  </section>

  <section class="card">
    <h2>Passwort ändern</h2>
    <input type="password" bind:value={pwOld} placeholder="Aktuelles Passwort" />
    <input type="password" bind:value={pwNew} placeholder="Neues Passwort" />
    <button type="button" onclick={changePw} disabled={!pwOld || !pwNew}>Ändern</button>
  </section>

  <section class="card">
    <h2>2FA (TOTP) — {s.totp_enabled ? "aktiv" : "nicht aktiv"}</h2>
    {#if !s.totp_enabled && !totpSetup}
      <button type="button" onclick={startTotp}>Einrichten</button>
    {:else if totpSetup}
      <img src={`data:image/png;base64,${totpSetup.qr_png_base64}`} alt="TOTP QR" />
      <p>Secret: <code>{totpSetup.secret}</code></p>
      <input bind:value={totpCode} placeholder="6-stelliger Code" inputmode="numeric" />
      <button type="button" onclick={confirmTotp} disabled={totpCode.length < 6}>Aktivieren</button>
    {/if}
  </section>

  <DataPortability />
{:else}
  <p>Lade Einstellungen…</p>
{/if}

<ModelMismatchDialog
  open={mismatch !== null}
  mismatch={mismatch ?? { old_model: "", new_model: "", affected_entries: 0 }}
  onRevert={async () => {
    if (!mismatch) return;
    await api("/api/settings", { method: "PUT", body: { embed_model: mismatch.old_model } });
    mismatch = null;
    await load();
    await loadStatus();
  }}
  onReindex={async () => {
    await reindexEmbeddings();
    mismatch = null;
    await loadStatus();
  }}
  onLater={() => (mismatch = null)}
/>

<style>
  .msg { color: var(--accent); padding: 0.5rem; }
  .card {
    margin: 1rem 0;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  fieldset {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin: 0.5rem 0;
    padding: 0.75rem;
  }
  fieldset legend { font-weight: 600; padding: 0 0.5rem; }
  label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    margin: 0.3rem 0;
  }
  img { max-width: 240px; }
  .muted { color: var(--muted); font-size: 0.85em; margin-left: 0.5em; }
  .env-hint {
    display: block;
    margin-top: 0.25rem;
    color: var(--muted, #888);
    font-size: 0.85rem;
  }
  .prompt-section { margin-top: 1rem; }
  .prompt-section legend { font-weight: 600; }
  .preset-buttons {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0.4rem 0 0.6rem;
  }
  .preset-buttons button {
    padding: 0.3rem 0.7rem;
    font-size: 0.9rem;
  }
</style>
