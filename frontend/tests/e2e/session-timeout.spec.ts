import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.skip(!process.env.E2E_LIVE, "requires running backend");

test("countdown is visible after login", async ({ page }) => {
  await login(page);
  await expect(page.locator(".countdown")).toBeVisible();
});
