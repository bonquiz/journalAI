<script lang="ts">
  import { get } from "svelte/store";
  import { goto } from "$app/navigation";
  import { api } from "$lib/api";
  import { finalize, streamChat } from "$lib/chat";
  import ChatMessage from "$lib/components/ChatMessage.svelte";
  import PreviewModal from "$lib/components/PreviewModal.svelte";
  import TextOrVoiceInput from "$lib/components/TextOrVoiceInput.svelte";
  import { chatDraft, resetChatDraft } from "$lib/stores/chatDraft";

  let input = $state("");
  let streaming = $state(false);
  let preview = $state<{ title: string; content: string; tags: string[]; entry_date: string } | null>(null);
  let rawTranscript = $state<string | null>(null);
  let errorMsg: string | null = $state(null);

  async function send() {
    if (!input.trim() || streaming) return;
    errorMsg = null;
    const userMsg = { role: "user" as const, content: input };
    if (!rawTranscript) rawTranscript = input;
    chatDraft.update((m) => [...m, userMsg, { role: "assistant", content: "" }]);
    const msgs = get(chatDraft).slice(0, -1).map((m) => ({ role: m.role, content: m.content }));
    input = "";
    streaming = true;
    try {
      for await (const tok of streamChat(msgs)) {
        chatDraft.update((m) => {
          m[m.length - 1] = { role: "assistant", content: m[m.length - 1].content + tok };
          return m;
        });
      }
    } catch {
      errorMsg = "Chat fehlgeschlagen.";
    } finally {
      streaming = false;
    }
  }

  async function save() {
    errorMsg = null;
    try {
      const msgs = get(chatDraft).map((m) => ({ role: m.role, content: m.content }));
      preview = await finalize(msgs);
    } catch {
      errorMsg = "Finalisieren fehlgeschlagen.";
    }
  }

  async function confirm() {
    if (!preview) return;
    const chat = get(chatDraft).map((m) => ({ role: m.role, content: m.content }));
    await api("/api/entries", {
      method: "POST",
      body: { ...preview, raw_transcript: rawTranscript, chat_history: chat },
    });
    resetChatDraft();
    goto("/entries");
  }
</script>

<h1>Neuer Eintrag</h1>

{#each $chatDraft as m, i (i)}
  <ChatMessage role={m.role} content={m.content} />
{/each}

<TextOrVoiceInput bind:value={input} placeholder="Diktat oder Text…" onsubmit={send} />

{#if errorMsg}<p class="err">{errorMsg}</p>{/if}

{#if $chatDraft.length >= 2 && !streaming}
  <button type="button" onclick={save} class="save-btn">
    Eintrag jetzt speichern
  </button>
{/if}

{#if preview}
  <PreviewModal
    bind:entry={preview}
    oncancel={() => (preview = null)}
    onconfirm={confirm}
  />
{/if}

<style>
  .save-btn { margin-top: 1rem; width: 100%; }
  .err { color: #b22; }
</style>
