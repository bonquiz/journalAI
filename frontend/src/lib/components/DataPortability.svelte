<script lang="ts">
  import { exportUrl } from "$lib/portability";
</script>

<section class="card">
  <h2>Datenportabilität</h2>

  <div class="block">
    <h3>Export</h3>
    <p class="muted">
      Lade alle Einträge und Tags als ZIP mit <code>entries.json</code> (Format v1) herunter.
    </p>
    <a class="btn" href={exportUrl()} download>Export herunterladen (.zip)</a>
  </div>
</section>

<style>
  .card {
    margin: 1rem 0;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
  }
  .block { margin-bottom: 1rem; }
  .block:last-child { margin-bottom: 0; }
  h3 { margin: 0 0 0.35rem; font-size: 1rem; }
  .muted { color: var(--muted); font-size: 0.9em; margin: 0 0 0.6rem; }
  .btn {
    display: inline-block;
    padding: 0.6rem 1rem;
    min-height: 44px;
    background: var(--accent);
    color: #fff;
    border-radius: var(--radius);
    text-decoration: none;
  }
</style>
