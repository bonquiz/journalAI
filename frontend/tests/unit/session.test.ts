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

  it("reloads when fetch receives an opaqueredirect (manual-redirect 3xx)", async () => {
    // Response cannot be constructed with type: "opaqueredirect" directly;
    // fake just enough of the Response shape.
    const fakeResponse = {
      type: "opaqueredirect",
      status: 0,
      ok: false,
      redirected: false,
      url: "",
      headers: new Headers(),
    } as unknown as Response;
    globalThis.fetch = vi.fn().mockResolvedValue(fakeResponse) as typeof fetch;

    await expect(session.login("testpw")).rejects.toThrow("gateway reauth required");
    expect(window.location.reload).toHaveBeenCalledOnce();
  });

  it("reloads when fetch follows a redirect to a different origin", async () => {
    const fakeResponse = {
      type: "basic",
      status: 200,
      ok: true,
      redirected: true,
      url: "https://bonquiz.cloudflareaccess.com/cdn-cgi/access/login/diary",
      headers: new Headers(),
    } as unknown as Response;
    globalThis.fetch = vi.fn().mockResolvedValue(fakeResponse) as typeof fetch;

    await expect(session.login("testpw")).rejects.toThrow("gateway reauth required");
    expect(window.location.reload).toHaveBeenCalledOnce();
  });
});
