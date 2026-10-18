import { test, expect, type Page } from "@playwright/test";
import { open, prepare } from "./fixtures";

const focused = (page: Page) => page.evaluate(() => {
  const el = document.activeElement as HTMLElement | null;
  return el ? { tag: el.tagName, id: el.id, view: el.dataset.view || "", cls: el.className || "" } : null;
});

async function tabUntil(page: Page, hit: (f: NonNullable<Awaited<ReturnType<typeof focused>>>) => boolean, max = 40) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const f = await focused(page);
    if (f && hit(f)) return f;
  }
  throw new Error("keyboard never reached the target");
}

test("keyboard reaches the nav, the primary button and the palette; the focus ring shows", async ({ page }) => {
  await prepare(page);
  await open(page, "student", "overview");

  const nav = await tabUntil(page, (f) => f.tag === "A" && f.view !== "");
  expect(nav.view).toBe("overview");
  const ring = await page.evaluate(() => {
    const cs = getComputedStyle(document.activeElement as HTMLElement);
    return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) };
  });
  expect(ring.style).not.toBe("none");
  expect(ring.width).toBeGreaterThanOrEqual(2);

  await tabUntil(page, (f) => f.tag === "A" && f.cls.split(" ").includes("btn") && !f.cls.split(" ").includes("secondary"));

  await page.keyboard.press("Control+k");
  await expect(page.locator("#pal")).toBeVisible();
  await expect(page.locator("#palIn")).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.locator("#pal")).toBeHidden();
});

const REASONS: Array<{ fixture: string; reason: string }> = [
  { fixture: "empty", reason: "עוד לא נבחרה תיקיית בית" },
  { fixture: "home-unreachable", reason: "תיקיית הבית לא נמצאה" },
  { fixture: "python-missing", reason: "Python לא מותקן" },
];

for (const { fixture, reason } of REASONS) {
  test(`${fixture}: Setup comes first in the nav and states the plain reason`, async ({ page }) => {
    await prepare(page);
    await open(page, fixture, "overview");
    const first = page.locator("#nav a").first();
    await expect(first).toHaveAttribute("data-view", "setup");
    await expect(page.locator("#view .banner a[href=\"#setup\"]")).toBeVisible();  // the Overview banner points to it
    await first.click();
    await expect(page.locator("#view h1")).toHaveText("הגדרה");
    await expect(page.locator("#view")).toContainText(reason);
    await expect(first).toHaveAttribute("aria-current", "page");
  });
}
