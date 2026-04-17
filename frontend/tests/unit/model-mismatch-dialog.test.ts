import { describe, expect, test, afterEach, vi } from "vitest";
import { render, fireEvent, cleanup } from "@testing-library/svelte";
import ModelMismatchDialog from "../../src/lib/components/ModelMismatchDialog.svelte";

afterEach(() => cleanup());

describe("ModelMismatchDialog", () => {
  const base = {
    open: true,
    mismatch: { old_model: "old-m", new_model: "new-m", affected_entries: 5 },
    onRevert: vi.fn(),
    onReindex: vi.fn(),
    onLater: vi.fn(),
  };

  test("shows old, new, affected count", () => {
    const { getByText } = render(ModelMismatchDialog, { props: base });
    expect(getByText(/old-m/)).toBeTruthy();
    expect(getByText(/new-m/)).toBeTruthy();
    expect(getByText(/5/)).toBeTruthy();
  });

  test("revert button calls onRevert", async () => {
    const onRevert = vi.fn();
    const { getByRole } = render(ModelMismatchDialog, { props: { ...base, onRevert } });
    await fireEvent.click(getByRole("button", { name: /zurück zum alten/i }));
    expect(onRevert).toHaveBeenCalled();
  });

  test("reindex button calls onReindex", async () => {
    const onReindex = vi.fn();
    const { getByRole } = render(ModelMismatchDialog, { props: { ...base, onReindex } });
    await fireEvent.click(getByRole("button", { name: /neu indexieren/i }));
    expect(onReindex).toHaveBeenCalled();
  });
});
