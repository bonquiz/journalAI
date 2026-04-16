import { describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { toast } from "$lib/stores/toast";

describe("toast store", () => {
  it("starts empty", () => {
    toast.dismissAll();
    expect(get(toast)).toEqual([]);
  });

  it("push adds a toast with id + level + message", () => {
    toast.dismissAll();
    toast.info("hallo");
    const items = get(toast);
    expect(items).toHaveLength(1);
    expect(items[0].level).toBe("info");
    expect(items[0].message).toBe("hallo");
    expect(typeof items[0].id).toBe("string");
  });

  it("success and error levels are settable", () => {
    toast.dismissAll();
    toast.success("ok");
    toast.error("oh no");
    const levels = get(toast).map((t) => t.level);
    expect(levels).toContain("success");
    expect(levels).toContain("error");
  });

  it("dismiss removes a specific toast by id", () => {
    toast.dismissAll();
    toast.info("one");
    toast.info("two");
    const items = get(toast);
    toast.dismiss(items[0].id);
    const remaining = get(toast);
    expect(remaining).toHaveLength(1);
    expect(remaining[0].message).toBe("two");
  });

  it("auto-dismiss removes toast after timeout", async () => {
    vi.useFakeTimers();
    toast.dismissAll();
    toast.info("short", 1000);
    expect(get(toast)).toHaveLength(1);
    vi.advanceTimersByTime(1100);
    expect(get(toast)).toHaveLength(0);
    vi.useRealTimers();
  });
});
