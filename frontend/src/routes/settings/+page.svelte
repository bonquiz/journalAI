<script lang="ts">
  import { onMount } from "svelte";
  import { api } from "$lib/api";

  type SettingsOut = {
    stt_base_url: string | null; stt_api_key_masked: string | null; stt_model: string | null;
    chat_base_url: string | null; chat_api_key_masked: string | null; chat_model: string | null;
    embed_base_url: string | null; embed_api_key_masked: string | null; embed_model: string | null;
    tts_base_url: string | null; tts_api_key_masked: string | null; tts_model: string | null;
    system_prompt: string | null;
    totp_enabled: boolean;
  };

  let s = $state<SettingsOut | null>(null);
  let form = $state<Record<string, string>>({});
  let pwOld = $state("");
  let pwNew = $state("");
  let totpSetup = $state<{ secret: string; qr_png_base64: string } | null>(null);
  let totpCode = $state("");
  let msg: string | null = $state(null);

  async function load() {
    s = await api<SettingsOut>("/api/settings");
  }

  onMount(load);

  async function saveEndpoints() {
    msg = null;
    await api("/api/settings", { method: "PUT", body: form });
    form = {};
    await load();
    msg = "Einstellungen gespeichert.";
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
        </label>
        <label>
          API Key
          <input type="password" bind:value={form[`${cap}_api_key`]}
                 placeholder={s[`${cap}_api_key_masked`] ?? "-"} />
        </label>
        <label>
          Model
          <input bind:value={form[`${cap}_model`]} placeholder={s[`${cap}_model`] ?? ""} />
        </label>
      </fieldset>
    {/each}
    <label>
      System-Prompt
      <textarea bind:value={form.system_prompt} rows="6" placeholder={s.system_prompt ?? ""}></textarea>
    </label>
    <button type="button" onclick={saveEndpoints}>Speichern</button>
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
{:else}
  <p>Lade Einstellungen…</p>
{/if}

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
</style>
