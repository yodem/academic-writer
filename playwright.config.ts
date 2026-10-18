import { defineConfig } from "@playwright/test";

const KEY = "e2e-key-0123456789abcdef0123456789";
const NOW = "2026-10-16T18:00:00+03:00";
const PORT = 8765;

export default defineConfig({
  testDir: "tests/e2e/dashboard",
  testMatch: /.*\.spec\.ts/,
  fullyParallel: false,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, extraHTTPHeaders: {} },
  webServer: {
    command: `python3 tests/e2e/dashboard/serve_fixture.py --fixture student --port ${PORT} --key ${KEY} --now ${NOW}`,
    url: `http://127.0.0.1:${PORT}/?key=${KEY}`,
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    { name: "chromium", use: { browserName: "chromium" } },
    { name: "firefox", use: { browserName: "firefox" } },
  ],
});
