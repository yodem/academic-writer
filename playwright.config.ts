import { defineConfig } from "@playwright/test";
import { INSTANCES, KEY, NOW, workdir } from "./tests/e2e/dashboard/fixtures";

export default defineConfig({
  testDir: "tests/e2e/dashboard",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  reporter: [["list"]],
  snapshotPathTemplate: "{testDir}/__screenshots__/{arg}{ext}",
  expect: { toHaveScreenshot: { maxDiffPixelRatio: 0.002, animations: "disabled" } },
  use: {
    baseURL: `http://127.0.0.1:${INSTANCES.student.port}`,
    extraHTTPHeaders: {},
    locale: "he-IL",
    timezoneId: "Asia/Jerusalem",
  },
  // One DashboardServer per fixture instance, each on its own port with a fixed clock (see fixtures.ts).
  webServer: Object.entries(INSTANCES).map(([name, { fixture, port }]) => ({
    command: `python3 tests/e2e/dashboard/serve_fixture.py --fixture ${fixture} --port ${port} --key ${KEY} --now ${NOW} --workdir ${JSON.stringify(workdir(name))}`,
    url: `http://127.0.0.1:${port}/?key=${KEY}`,
    reuseExistingServer: false,
    timeout: 90_000, // a fixture server may wait out TIME-WAIT from the previous run (serve_fixture.py)
  })),
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "firefox", use: { browserName: "firefox" } },
  ],
});
