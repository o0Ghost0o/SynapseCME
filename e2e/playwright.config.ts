import { defineConfig, devices } from '@playwright/test'

// Browser-level E2E against the live stack (Caddy gateway serves the Nuxt app
// and proxies /api/* + /ws/*). Env overrides:
//   E2E_BASE_URL      default http://localhost:3000
//   E2E_ADMIN_USER    default admin
//   E2E_ADMIN_PASSWORD default synapse-admin
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 150_000,
  expect: { timeout: 90_000 },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.ts/ },
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'tests/.auth/admin.json',
      },
      dependencies: ['setup'],
      testIgnore: /auth\.setup\.ts/,
    },
  ],
})
