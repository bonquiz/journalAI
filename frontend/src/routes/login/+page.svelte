<script lang="ts">
  import { goto } from "$app/navigation";
  import { session } from "$lib/stores/session";

  let password = $state("");
  let totp = $state("");
  let error: string | null = $state(null);
  let submitting = $state(false);

  async function submit(e: SubmitEvent) {
    e.preventDefault();
    error = null;
    submitting = true;
    try {
      await session.login(password, totp || undefined);
      goto("/");
    } catch {
      error = "Login fehlgeschlagen.";
    } finally {
      submitting = false;
    }
  }
</script>

<form onsubmit={submit} class="login-form">
  <h1>Anmelden</h1>
  <label>
    Passwort
    <input type="password" bind:value={password} required autofocus />
  </label>
  <label>
    TOTP (falls aktiv)
    <input bind:value={totp} inputmode="numeric" placeholder="6-stelliger Code" />
  </label>
  {#if error}<p class="err">{error}</p>{/if}
  <button type="submit" disabled={submitting || !password}>
    {submitting ? "..." : "Anmelden"}
  </button>
</form>

<style>
  .login-form {
    max-width: 320px;
    margin: 3rem auto;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .login-form label {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .err {
    color: #b22;
    margin: 0;
  }
</style>
