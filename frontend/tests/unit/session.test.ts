import { describe, expect, it } from "vitest";
import { get } from "svelte/store";
import { session } from "$lib/stores/session";

describe("session store", () => {
  it("starts unauthenticated", () => {
    const s = get(session);
    expect(s.authenticated).toBe(false);
    expect(s.idleSecondsLeft).toBeGreaterThan(0);
  });
});
