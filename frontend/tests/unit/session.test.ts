import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { session } from "$lib/stores/session";

describe("session store", () => {
  it("starts unauthenticated", () => {
    const s = get(session);
    expect(s.authenticated).toBe(false);
    expect(s.idleSecondsLeft).toBeGreaterThan(0);
  });
});

describe("session.login", () => {
  const originalFetch = globalThis.fetch;
  const originalLocation = window.location;

  beforeEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, reload: vi.fn() },
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: originalLocation,
    });
  });

  it("reloads when Cloudflare Access returns 401 with WWW-Authenticate: Cloudflare-Access", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(null, {
        status: 401,
        headers: {
          "www-authenticate":
            'Cloudflare-Access resource_metadata="https://diary.example/.well-known/"',
        },
      }),
    ) as typeof fetch;

    await expect(session.login("testpw")).rejects.toThrow("gateway reauth required");
    expect(window.location.reload).toHaveBeenCalledOnce();
  });

  it("throws generic login failed on backend 401 without gateway headers", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid credentials" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    ) as typeof fetch;

    await expect(session.login("wrongpw")).rejects.toThrow("login failed");
    expect(window.location.reload).not.toHaveBeenCalled();
  });
});
