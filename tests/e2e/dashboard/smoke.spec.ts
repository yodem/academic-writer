import { test, expect } from "@playwright/test";

const KEY = "e2e-key-0123456789abcdef0123456789";

test("GET /?key= renders an RTL page", async ({ page }) => {
  await page.goto(`/?key=${KEY}`);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});
