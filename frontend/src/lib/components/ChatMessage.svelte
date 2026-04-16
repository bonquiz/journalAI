<script lang="ts">
  const { role, content }: { role: string; content: string } = $props();
</script>

<article class="msg {role}">
  <header>{role === "user" ? "Du" : "Assistent"}</header>
  <div class="body">{content}</div>
</article>

<style>
  .msg { margin: 0.75rem 0; padding: 0.75rem; border-radius: var(--radius); }
  .msg.user { background: #eef2f6; }
  .msg.assistant { background: #f5f7fa; }
  .msg header { font-weight: 600; font-size: 0.85em; color: var(--muted); margin-bottom: 0.25rem; }
  .body { white-space: pre-wrap; }
</style>
