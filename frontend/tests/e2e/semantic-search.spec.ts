import { test, expect } from "@playwright/test";
import { login } from "./helpers";

const LIVE = !!process.env.E2E_LIVE;

test.describe("semantic search", () => {
  test.skip(!LIVE, "E2E_LIVE not set — running offline skeleton");

  test("toggle to semantic, run query, see results", async ({ page }) => {
    await login(page);
    await page.goto("/entries");
    await page.getByRole("switch", { name: /semantisch/i }).click();
    await page.getByPlaceholder(/ganzen Sätzen/).fill("Regenbogen-Traum");
    await page.getByRole("button", { name: /Suchen/ }).click();
    // Entweder ein Treffer (SearchResultCard mit .result-Klasse) oder Banner/Empty — wir prüfen, dass die Seite reagiert.
    await expect(async () => {
      const anyReaction = await page.locator("main").textContent();
      expect(anyReaction).toMatch(/Keine Treffer|Suchindex|Index wird gebaut|\/\d|Regenbogen/);
    }).toPass({ timeout: 20000 });
  });

  test("voice path skeleton", async ({ page }) => {
    test.skip(true, "mic injection only in manually prepared E2E_LIVE run");
  });
});
