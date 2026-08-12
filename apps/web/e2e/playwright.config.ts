import { defineConfig, devices } from "@playwright/test";

const baseURL = `http://localhost:${process.env.E2E_WEB_PORT ?? "3000"}`;

export default defineConfig({
  testDir: "./specs",
  globalSetup: "./global-setup",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 2 : 0,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: process.env.CI ? [["list"], ["github"]] : [["list"]],
  outputDir: "test-results",
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 900 },
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 30_000,
    navigationTimeout: 45_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
