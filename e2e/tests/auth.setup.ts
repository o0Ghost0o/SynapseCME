import { test as setup } from '@playwright/test'

// Logs in once through the real UI and saves the session for all authed tests.
const user = process.env.E2E_ADMIN_USER ?? 'admin'
const password = process.env.E2E_ADMIN_PASSWORD ?? 'synapse-admin'

setup('login como admin', async ({ page }) => {
  await page.goto('/login')
  await page.getByLabel('Usuario').fill(user)
  await page.getByLabel('Contraseña').fill(password)
  await page.getByRole('button', { name: 'Iniciar sesión' }).click()
  await page.waitForURL('**/dashboard')
  await page.context().storageState({ path: 'tests/.auth/admin.json' })
})
