<script lang="ts">
  import "../app.css";
  let { children } = $props();
</script>

<header class="topbar">
  <a href="/">journalAI</a>
</header>

<main>
  {@render children()}
</main>
