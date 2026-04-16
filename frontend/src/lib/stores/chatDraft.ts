import { writable } from "svelte/store";

type Msg = { role: "user" | "assistant"; content: string };
export const chatDraft = writable<Msg[]>([]);
export function resetChatDraft() { chatDraft.set([]); }
