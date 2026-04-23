import { clearCache as clearTtsCache } from "$lib/tts";
import { writable } from "svelte/store";

type SessionState = {
  authenticated: boolean;
  idleSecondsLeft: number;
};

const IDLE_LIMIT_S = 20 * 60; // matches backend default SESSION_IDLE_MINUTES

function isGatewayChallenge(r: Response): boolean {
  const www = r.headers.get("www-authenticate") ?? "";
  if (/^Cloudflare-Access/i.test(www)) return true;
  // Some gateways (and CF on certain paths) drop the header but set cf-mitigated
  // or return no body on the API path. Treat a non-JSON content-type as a tell.
  const ct = r.headers.get("content-type") ?? "";
  if (r.headers.get("cf-mitigated") && !ct.includes("application/json")) return true;
  return false;
}

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
      update((s) => {
        const next = Math.max(0, s.idleSecondsLeft - 1);
        if (next === 0 && s.authenticated) {
          // Fire-and-forget: the logout() call will itself stop the timer and
          // navigate to /login. Scheduled as a microtask so we don't mutate
          // the store while inside an `update` callback.
          queueMicrotask(() => {
            void logout();
          });
        }
        return { ...s, idleSecondsLeft: next };
      });
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
    if (!r.ok) {
      // If an upstream access gateway (e.g. Cloudflare Access) has expired our
      // SSO token, it intercepts the API call with 401 + WWW-Authenticate
      // instead of redirecting. A full page reload lets the gateway redirect
      // through its own login flow.
      if (r.status === 401 && isGatewayChallenge(r)) {
        if (typeof window !== "undefined") window.location.reload();
        throw new Error("gateway reauth required");
      }
      throw new Error("login failed");
    }
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
    clearTtsCache();
    stopTicking();
    set({ authenticated: false, idleSecondsLeft: IDLE_LIMIT_S });
    if (typeof window !== "undefined") window.location.href = "/login";
  }

  return { subscribe, refresh, login, logout };
}

export const session = createSession();
