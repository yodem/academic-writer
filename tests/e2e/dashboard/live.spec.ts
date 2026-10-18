import * as fs from "node:fs";
import * as path from "node:path";
import { test, expect } from "@playwright/test";
import { liveRun, open, prepare, registry } from "./fixtures";

// These specs change the fixture's files, so each browser project has its own copy of the student fixture.
test.describe.configure({ mode: "serial" });
const instance = (name: string) => `student-${name}`;

test("a new line in the in-progress activity.jsonl advances the Writing page without a reload", async ({ page }, info) => {
  const inst = instance(info.project.name);
  await prepare(page);
  await open(page, inst, "writing");
  const meta = page.locator("article.run .meta").first();
  await expect(meta).toContainText("שלב 3 מתוך 6");
  await page.evaluate(() => { (window as unknown as { __noReload: boolean }).__noReload = true; });

  fs.appendFileSync(liveRun(inst), JSON.stringify({
    v: 1, ts: "2026-10-16T17:55:00.000Z", run: "R", flow: "write", kind: "step_start", step: "redraft",
  }) + "\n");

  await expect(meta).toContainText("שלב 4 מתוך 6", { timeout: 5000 });
  expect(await page.evaluate(() => (window as unknown as { __noReload?: boolean }).__noReload)).toBe(true);
});

test("editing a course JSON changes its Courses card", async ({ page }, info) => {
  const inst = instance(info.project.name);
  await prepare(page);
  await open(page, inst, "courses");
  await expect(page.locator("#view")).toContainText("Beta course");
  const file = path.join(registry(inst), "beta.json");
  const data = JSON.parse(fs.readFileSync(file, "utf8"));
  data.name = "Beta course renamed live";
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
  await expect(page.locator("#view")).toContainText("Beta course renamed live", { timeout: 5000 });
});
