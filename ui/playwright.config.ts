import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  outputDir: '../.artifacts/node-editor/playwright-results',
  preserveOutput: 'always',
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  timeout: 30_000,
  reporter: [
    ['list'],
    ['html', { outputFolder: '../.artifacts/node-editor/playwright-report', open: 'never' }],
  ],
  use: {
    ...devices['Desktop Chrome'],
    viewport: { width: 1600, height: 1000 },
    baseURL: 'http://127.0.0.1:4173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: false,
    timeout: 30_000,
  },
});
