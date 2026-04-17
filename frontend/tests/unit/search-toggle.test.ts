import { describe, expect, test, afterEach } from "vitest";
import { render, fireEvent, cleanup } from "@testing-library/svelte";
import SearchToggle from "../../src/lib/components/SearchToggle.svelte";

afterEach(() => cleanup());

describe("SearchToggle", () => {
  test("renders ARIA switch with value=keyword", () => {
    const { getByRole } = render(SearchToggle, { props: { value: "keyword", onChange: () => {} } });
    const el = getByRole("switch");
    expect(el.getAttribute("aria-checked")).toBe("false");
  });

  test("onChange toggles to semantic", async () => {
    let called: string | null = null;
    const { getByRole } = render(SearchToggle, {
      props: { value: "keyword", onChange: (v: any) => (called = v) },
    });
    await fireEvent.click(getByRole("switch"));
    expect(called).toBe("semantic");
  });

  test("value=semantic → aria-checked=true", () => {
    const { getByRole } = render(SearchToggle, { props: { value: "semantic", onChange: () => {} } });
    expect(getByRole("switch").getAttribute("aria-checked")).toBe("true");
  });
});
