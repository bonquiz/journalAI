import { writable } from "svelte/store";

type SessionState = {
  authenticated: boolean;
  idleSecondsLeft: number;
};

const IDLE_LIMIT_S = 10 * 60; // matches backend default SESSION_IDLE_MINUTES

function createSession() {
  const { subscribe, set, update } = writable<SessionState>({
    authenticated: false,
    idleSecondsLeft: IDLE_LIMIT_S,
  });

  let tickTimer: ReturnType<typeof setInterval> | null = null;
  let activityHandler: (() => void) | null = null;

  function startTicking() {
    stopTicking();
    if (typeof document === "undefined") return;
    tickTimer = setInterval(() => {
      update((s) => ({ ...s, idleSecondsLeft: Math.max(0, s.idleSecondsLeft - 1) }));
    }, 1000);
    activityHandler = () =>
      update((s) => (s.authenticated ? { ...s, idleSecondsLeft: IDLE_LIMIT_S } : s));
    for (const ev of ["click", "keydown", "touchstart"]) {
      document.addEventListener(ev, activityHandler, { passive: true });
    }
  }

  function stopTicking() {
    if (tickTimer) clearInterval(tickTimer);
    tickTimer = null;
    if (activityHandler && typeof document !== "undefined") {
      for (const ev of ["click", "keydown", "touchstart"]) {
        document.removeEventListener(ev, activityHandler);
      }
    }
    activityHandler = null;
  }

  async function refresh() {
    if (typeof window === "undefined") return;
    try {
      const r = await fetch("/api/tags", { credentials: "same-origin" });
      const authed = r.status === 200;
      set({ authenticated: authed, idleSecondsLeft: IDLE_LIMIT_S });
      if (authed) startTicking();
      else stopTicking();
    } catch {
      set({ authenticated: false, idleSecondsLeft: IDLE_LIMIT_S });
      stopTicking();
    }
  }

  async function login(password: string, totp?: string): Promise<void> {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password, totp }),
    });
    if (!r.ok) throw new Error("login failed");
    set({ authenticated: true, idleSecondsLeft: IDLE_LIMIT_S });
    startTicking();
  }

  async function logout(): Promise<void> {
    const csrf =
      typeof document !== "undefined"
        ? (document.cookie.match(/(?:^|;\s*)csrf=([^;]*)/)?.[1] ?? "")
        : "";
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrf },
    });
    stopTicking();
    set({ authenticated: false, idleSecondsLeft: IDLE_LIMIT_S });
    if (typeof window !== "undefined") window.location.href = "/login";
  }

  return { subscribe, refresh, login, logout };
}

export const session = createSession();
