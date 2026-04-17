import { test, expect } from "@playwright/test";

const LIVE = !!process.env.E2E_LIVE;

test.describe("semantic search", () => {
  test.skip(!LIVE, "E2E_LIVE not set — running offline skeleton");

  test("toggle to semantic, run query, see results", async ({ page }) => {
    await page.goto("/entries");
    await page.getByRole("switch", { name: /semantisch/i }).click();
    await page.getByPlaceholder(/ganzen Sätzen/).fill("Regenbogen-Traum");
    await page.getByRole("button", { name: /Suchen/ }).click();
    await expect(page.locator(".card").first()).toBeVisible({ timeout: 15000 });
  });

  test("voice path skeleton", async ({ page }) => {
    test.skip(true, "mic injection only in manually prepared E2E_LIVE run");
  });
});
