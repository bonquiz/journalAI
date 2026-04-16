<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { session } from "$lib/stores/session";
  import SessionCountdown from "$lib/components/SessionCountdown.svelte";
  import ToastContainer from "$lib/components/ToastContainer.svelte";

  let { children } = $props();

  onMount(async () => {
    await session.refresh();

    if ("serviceWorker" in navigator) {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    }
  });
</script>

<ToastContainer />

<header class="topbar">
  <a href="/" class="brand">journalAI</a>
  {#if $session.authenticated}
    <nav>
      <a href="/entries">Einträge</a>
      <a href="/tags">Tags</a>
      <a href="/settings">Einstellungen</a>
      <button type="button" onclick={() => session.logout()} class="link">Logout</button>
      <SessionCountdown />
    </nav>
  {/if}
</header>

<main>
  {@render children()}
</main>

<style>
  .topbar {
    flex-wrap: wrap;
    gap: 0.5rem 1rem;
  }
  .topbar .brand {
    font-weight: 600;
    text-decoration: none;
  }
  .topbar nav {
    display: flex;
    align-items: center;
    gap: 0.75rem 1rem;
    flex-wrap: wrap;
  }
  .link {
    background: transparent;
    color: var(--accent);
    border: none;
    padding: 0;
    cursor: pointer;
    font: inherit;
    min-height: 44px;
  }
  nav a {
    min-height: 44px;
    display: inline-flex;
    align-items: center;
  }

  @media (max-width: 600px) {
    .topbar { padding: 0.5rem 0.75rem; }
    .topbar nav { gap: 0.5rem 0.75rem; font-size: 0.95em; }
  }
</style>
