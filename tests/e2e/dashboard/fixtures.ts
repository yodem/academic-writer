import * as os from "node:os";
import * as path from "node:path";
import type { Page } from "@playwright/test";

export const KEY = "e2e-key-0123456789abcdef0123456789";
export const NOW = "2026-10-16T18:00:00+03:00";

/** First port of the block of seven; set AW_E2E_PORT_BASE when another run on the machine already holds 8765-8771. */
const BASE = Number(process.env.AW_E2E_PORT_BASE || 8765);

export type Fixture = "student" | "lecturer" | "empty" | "home-unreachable" | "python-missing";

/** One server per instance. `student-chromium` and `student-firefox` are private copies of the student fixture
 *  for the specs that change files (live, actions), so they never disturb the read-only page and baseline specs. */
export const INSTANCES: Record<string, { fixture: Fixture; port: number }> = {
  student: { fixture: "student", port: BASE + 0 },
  lecturer: { fixture: "lecturer", port: BASE + 1 },
  empty: { fixture: "empty", port: BASE + 2 },
  "home-unreachable": { fixture: "home-unreachable", port: BASE + 3 },
  "python-missing": { fixture: "python-missing", port: BASE + 4 },
  "student-chromium": { fixture: "student", port: BASE + 5 },
  "student-firefox": { fixture: "student", port: BASE + 6 },
};

export const baseUrl = (instance: string) => `http://127.0.0.1:${INSTANCES[instance].port}`;
export const workdir = (instance: string) => path.join(os.tmpdir(), process.env.AW_E2E_PORT_BASE ? `aw-e2e-${BASE}` : "aw-e2e", instance);
export const registry = (instance: string) => path.join(workdir(instance), "root", "T1");
export const liveRun = (instance: string) =>
  path.join(workdir(instance), "ws", "עבודה-סמינריונית-פרשנות-ימי-הביניים-BIBL-204-final-draft-v3",
    ".academic-helper", "runs", "run-live", "activity.jsonl");

/** The nav (in order) each fixture's role and setup state must produce. */
export const NAV: Record<Fixture, string[]> = {
  student: ["overview", "timeline", "courses", "writing", "about"],
  lecturer: ["overview", "writing", "about"],
  empty: ["setup", "overview", "writing", "about"],
  "home-unreachable": ["setup", "overview", "timeline", "courses", "writing", "about"],
  "python-missing": ["setup", "overview", "timeline", "courses", "writing", "about"],
};

/** Every page a fixture shows, as a route, with the heading it must carry (`null`: only that one exists). */
export const PAGES: Record<Fixture, Array<{ route: string; heading: string | null }>> = {
  student: [
    { route: "overview", heading: null },
    { route: "timeline", heading: "ציר זמן" },
    { route: "courses", heading: "הקורסים שלי" },
    { route: "course/alpha", heading: "BIBL-204" },
    { route: "writing", heading: "כתיבה" },
    { route: "setup", heading: "הגדרה" },
    { route: "about", heading: "אודות" },
  ],
  lecturer: [
    { route: "overview", heading: null },
    { route: "writing", heading: "כתיבה" },
    { route: "setup", heading: "הגדרה" },
    { route: "about", heading: "אודות" },
  ],
  empty: [
    { route: "setup", heading: "הגדרה" },
    { route: "overview", heading: null },
    { route: "writing", heading: "כתיבה" },
    { route: "about", heading: "אודות" },
  ],
  "home-unreachable": [
    { route: "setup", heading: "הגדרה" },
    { route: "overview", heading: null },
    { route: "writing", heading: "כתיבה" },
    { route: "about", heading: "אודות" },
  ],
  "python-missing": [
    { route: "setup", heading: "הגדרה" },
    { route: "overview", heading: null },
    { route: "courses", heading: "הקורסים שלי" },
    { route: "about", heading: "אודות" },
  ],
};

export const WIDTHS = [360, 768, 1024, 1440];
export const THEMES = ["light", "dark"] as const;

/** Keeps the run offline and deterministic: web fonts are answered with an empty stylesheet (system fonts draw),
 *  and every console error or uncaught exception is collected. */
export async function prepare(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.fulfill({ status: 200, contentType: "text/css", body: "" }));
  return errors;
}

/** Open a route of an instance and wait until its page has drawn. */
export async function open(page: Page, instance: string, route: string) {
  await page.goto(`${baseUrl(instance)}/?key=${KEY}#${route}`);
  await page.locator("#view h1").first().waitFor({ state: "visible" });
  await page.evaluate(() => document.fonts.ready);
}
