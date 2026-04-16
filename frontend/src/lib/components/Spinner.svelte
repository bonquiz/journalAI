<script lang="ts">
  const { label = "Bitte warten", size = 16 }: { label?: string; size?: number } = $props();
</script>

<span class="spinner" role="status" aria-live="polite" aria-label={label}>
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity="0.25" stroke-width="3" />
    <path d="M12 3 a9 9 0 0 1 9 9" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
  </svg>
</span>

<style>
  .spinner {
    display: inline-flex;
    align-items: center;
  }
  .spinner svg {
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
