import { writable } from "svelte/store";

type Current = { id: string; element: HTMLAudioElement } | null;
const store = writable<Current>(null);

export const currentPlayback = { subscribe: store.subscribe };

export function setCurrent(id: string, element: HTMLAudioElement): void {
  store.update((prev) => {
    if (prev && prev.id !== id) {
      prev.element.pause();
    }
    return { id, element };
  });
}

export function stopAll(): void {
  store.update((prev) => {
    if (prev) prev.element.pause();
    return null;
  });
}

/**
 * Clear the current reference without calling pause.
 * Called from onDestroy of player components so the store doesn't retain
 * references to unmounted HTMLAudioElement instances.
 * If `id` is given, only clears when it matches.
 */
export function clearCurrent(id?: string): void {
  store.update((prev) => {
    if (prev === null) return null;
    if (id === undefined || prev.id === id) return null;
    return prev;
  });
}
