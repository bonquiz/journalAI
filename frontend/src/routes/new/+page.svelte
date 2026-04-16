<script lang="ts">
  import { get } from "svelte/store";
  import { goto } from "$app/navigation";
  import { api } from "$lib/api";
  import { finalize, streamChat } from "$lib/chat";
  import AutoPlayToggle from "$lib/components/AutoPlayToggle.svelte";
  import ChatMessage from "$lib/components/ChatMessage.svelte";
  import PlayMessageButton from "$lib/components/PlayMessageButton.svelte";
  import PreviewModal from "$lib/components/PreviewModal.svelte";
  import Spinner from "$lib/components/Spinner.svelte";
  import TextOrVoiceInput from "$lib/components/TextOrVoiceInput.svelte";
  import { chatDraft, resetChatDraft } from "$lib/stores/chatDraft";

  let input = $state("");
  let streaming = $state(false);
  let autoPlay = $state(false);
  let autoplayIndex: number | null = $state(null);
  let finalizing = $state(false);
  let saving = $state(false);
  let preview = $state<{ title: string; content: string; tags: string[]; entry_date: string } | null>(null);
  let rawTranscript = $state<string | null>(null);
  let errorMsg: string | null = $state(null);

  const busy = $derived(streaming || finalizing || saving);

  async function send() {
    if (!input.trim() || busy) return;
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
      if (autoPlay) {
        const list = get(chatDraft);
        const lastIdx = list.length - 1;
        const last = list[lastIdx];
        if (last && last.role === "assistant" && last.content.trim()) {
          autoplayIndex = lastIdx;
        }
      }
    } catch {
      errorMsg = "Chat fehlgeschlagen.";
    } finally {
      streaming = false;
    }
  }

  async function save() {
    errorMsg = null;
    finalizing = true;
    try {
      const msgs = get(chatDraft).map((m) => ({ role: m.role, content: m.content }));
      preview = await finalize(msgs);
    } catch {
      errorMsg = "Finalisieren fehlgeschlagen.";
    } finally {
      finalizing = false;
    }
  }

  async function confirm() {
    if (!preview) return;
    saving = true;
    try {
      const chat = get(chatDraft).map((m) => ({ role: m.role, content: m.content }));
      await api("/api/entries", {
        method: "POST",
        body: { ...preview, raw_transcript: rawTranscript, chat_history: chat },
      });
      resetChatDraft();
      goto("/entries");
    } catch {
      errorMsg = "Speichern fehlgeschlagen.";
      saving = false;
    }
  }
</script>

<h1>Neuer Eintrag</h1>
<AutoPlayToggle bind:value={autoPlay} />

{#each $chatDraft as m, i (i)}
  <ChatMessage role={m.role} content={m.content}>
    {#snippet children()}
      {#if m.role === "assistant" && m.content.trim()}
        <PlayMessageButton
          text={m.content}
          autoplay={autoplayIndex === i}
        />
      {/if}
    {/snippet}
  </ChatMessage>
{/each}

{#if streaming}
  <p class="status"><Spinner label="Assistent antwortet" /> <span>Assistent schreibt…</span></p>
{/if}

<TextOrVoiceInput bind:value={input} placeholder="Diktat oder Text…" onsubmit={send} />

{#if errorMsg}<p class="err">{errorMsg}</p>{/if}

{#if $chatDraft.length >= 2}
  <button type="button" onclick={save} class="save-btn" disabled={busy}>
    {#if finalizing}
      <Spinner label="Eintrag wird strukturiert" /> <span>Strukturiere Eintrag…</span>
    {:else}
      Eintrag jetzt speichern
    {/if}
  </button>
{/if}

{#if preview}
  <PreviewModal
    bind:entry={preview}
    {saving}
    oncancel={() => (preview = null)}
    onconfirm={confirm}
  />
{/if}

<style>
  .save-btn {
    margin-top: 1rem;
    width: 100%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }
  .save-btn:disabled { opacity: 0.7; cursor: progress; }
  .status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--muted);
    margin: 0.5rem 0.25rem;
    font-size: 0.9em;
  }
  .err { color: #b22; }
</style>
