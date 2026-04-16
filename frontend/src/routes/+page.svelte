<script lang="ts">
  import { onMount } from "svelte";
  import { goto } from "$app/navigation";
  import { session } from "$lib/stores/session";

  onMount(async () => {
    await session.refresh();
    if (!$session.authenticated) goto("/login");
  });
</script>

<section class="home">
  <h1>Tagebuch</h1>
  <a class="big" href="/new">Eintrag erfassen</a>
  <a class="big" href="/entries">Einträge ansehen</a>
</section>

<style>
  .home {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    max-width: 420px;
    margin: 3rem auto;
  }
  .big {
    display: block;
    padding: 1.5rem;
    background: var(--accent);
    color: #fff;
    text-align: center;
    text-decoration: none;
    border-radius: var(--radius);
    font-size: 1.2rem;
  }
  .big:hover { opacity: 0.9; }
</style>
