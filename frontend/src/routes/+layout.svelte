<script lang="ts">
  import "../app.css";
  import { onMount } from "svelte";
  import { session } from "$lib/stores/session";
  import SessionCountdown from "$lib/components/SessionCountdown.svelte";

  let { children } = $props();

  onMount(async () => {
    await session.refresh();
  });
</script>

<header class="topbar">
  <a href="/">journalAI</a>
  {#if $session.authenticated}
    <nav>
      <a href="/entries">Einträge</a>
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
  .topbar nav { display: flex; align-items: center; gap: 1rem; }
  .link { background: transparent; color: var(--accent); border: none; padding: 0; cursor: pointer; font: inherit; }
</style>
