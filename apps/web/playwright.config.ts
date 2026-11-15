import { defineConfig, devices } from "@playwright/test";

// The UI is tested against a mocked API (tests/e2e/mock.ts) so the suite is deterministic in
// CI. The same specs run against the real stack with E2E_BASE_URL=http://localhost:8000.
const base = process.env.E2E_BASE_URL;

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: base ?? "http://localhost:4173", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: base ? undefined : { command: "npx vite preview --port 4173", port: 4173, reuseExistingServer: true },
});
