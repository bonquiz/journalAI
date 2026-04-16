import { writable } from "svelte/store";

export type ToastLevel = "info" | "success" | "error";
export type Toast = { id: string; level: ToastLevel; message: string };

const { subscribe, update, set } = writable<Toast[]>([]);

const DEFAULT_TIMEOUT = 5000;
const ERROR_TIMEOUT = 8000;

function randomId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2);
}

function push(level: ToastLevel, message: string, timeoutMs?: number): string {
  const id = randomId();
  update((ts) => [...ts, { id, level, message }]);
  const ms = timeoutMs ?? (level === "error" ? ERROR_TIMEOUT : DEFAULT_TIMEOUT);
  if (ms > 0) setTimeout(() => dismiss(id), ms);
  return id;
}

function dismiss(id: string) {
  update((ts) => ts.filter((t) => t.id !== id));
}

function dismissAll() {
  set([]);
}

export const toast = {
  subscribe,
  info: (m: string, ms?: number) => push("info", m, ms),
  success: (m: string, ms?: number) => push("success", m, ms),
  error: (m: string, ms?: number) => push("error", m, ms),
  dismiss,
  dismissAll,
};
