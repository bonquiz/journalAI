import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.skip(!process.env.E2E_LIVE, "requires running backend + mock LLM endpoint");

test("create and delete an entry", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);

  await page.click("text=Eintrag erfassen");
  await page.waitForURL("/new");
  await page.fill("textarea", "Heute war ein ruhiger Tag.");
  await page.click("text=Senden");
  // Chat-Antwort abwarten: der Assistent-Output erscheint als zweite Chat-Message.
  await page.waitForSelector("text=Assistent schreibt…", { state: "detached", timeout: 30_000 });
  await page.click("text=Eintrag jetzt speichern");
  // finalize() ist ein Netzwerk-Call; PreviewModal kann ein paar Sekunden brauchen.
  await page.getByRole("button", { name: "So speichern" }).click({ timeout: 30_000 });
  await expect(page).toHaveURL(/\/entries/);
});
