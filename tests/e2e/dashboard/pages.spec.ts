import { test, expect } from "@playwright/test";
import { NAV, PAGES, THEMES, WIDTHS, open, prepare, type Fixture } from "./fixtures";

const fixtures = Object.keys(PAGES) as Fixture[];

for (const fixture of fixtures) {
  test.describe(`${fixture} pages`, () => {
    test(`nav is ${NAV[fixture].join(", ")}`, async ({ page }) => {
      await prepare(page);
      await open(page, fixture, PAGES[fixture][0].route);
      const ids = await page.locator("#nav a").evaluateAll((els) => els.map((a) => (a as HTMLElement).dataset.view));
      expect(ids).toEqual(NAV[fixture]);
    });

    for (const { route, heading } of PAGES[fixture]) {
      for (const scheme of THEMES) {
        for (const width of WIDTHS) {
          test(`${route} ${scheme} ${width}`, async ({ page }) => {
            const errors = await prepare(page);
            await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
            await page.setViewportSize({ width, height: 900 });
            await open(page, fixture, route);

            await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
            const h1 = page.locator("#view h1").first();
            await expect(h1).toBeVisible();
            if (heading) await expect(h1).toContainText(heading);
            else expect((await h1.innerText()).trim().length).toBeGreaterThan(0);

            // no page overflow at 360 (and at every other width): wide tables scroll inside their own box
            const over = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
            expect(over.sw, `no page overflow at ${width}: scrollWidth ${over.sw} > innerWidth ${over.iw}`).toBeLessThanOrEqual(over.iw);

            expect(errors, "console errors").toEqual([]);
          });
        }
      }
    }
  });
}

// The nav switch changes the theme and the choice survives a reload (stored per browser, never required).
test("theme switch toggles data-theme", async ({ page }) => {
  await prepare(page);
  await page.emulateMedia({ colorScheme: "light" });
  await open(page, "student", "overview");
  await page.locator("#themeBtn").click();
  const first = await page.locator("html").getAttribute("data-theme");
  await page.locator("#themeBtn").click();
  const second = await page.locator("html").getAttribute("data-theme");
  expect(first).not.toBe(second);
  expect([first, second].sort()).toEqual(["dark", "light"]);
});

// Visual baselines: Chromium only. student: every page; lecturer: overview and writing; at 360 and 1440, both themes.
const BASELINES: Array<{ fixture: Fixture; route: string }> = [
  ...PAGES.student.map((p) => ({ fixture: "student" as Fixture, route: p.route })),
  { fixture: "lecturer", route: "overview" },
  { fixture: "lecturer", route: "writing" },
];

test.describe("visual baselines", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "baselines are Chromium only");
  for (const { fixture, route } of BASELINES) {
    for (const scheme of THEMES) {
      for (const width of [360, 1440]) {
        const name = `${fixture}-${route.replace("/", "-")}-${width}-${scheme}.png`;
        test(`baseline ${name}`, async ({ page }) => {
          await prepare(page);
          await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
          await page.setViewportSize({ width, height: 900 });
          await open(page, fixture, route);
          // grow the viewport to the whole page: fixed layers (the paper grain, the 360 px bottom bar) then cover it exactly
          const height = await page.evaluate(() => document.documentElement.scrollHeight);
          await page.setViewportSize({ width, height });
          await page.waitForTimeout(300);
          await expect(page).toHaveScreenshot(name, { stylePath: "tests/e2e/dashboard/screenshot.css" });
        });
      }
    }
  }
});

