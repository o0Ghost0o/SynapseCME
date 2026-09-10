import { expect, test } from '@playwright/test'

// Flujos de autenticación y redirecciones del middleware global.
// El proyecto 'chromium' ya trae sesión (storageState), así que las
// redirecciones de no-autenticado se prueban borrando el estado en el test.

test.describe('autenticación', () => {
  test('raíz redirige a /login cuando no hay sesión', async ({ browser, baseURL }) => {
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await ctx.newPage()
    await page.goto('/')
    await page.waitForURL('**/login**')
    expect(new URL(page.url()).pathname).toBe('/login')
    await ctx.close()
  })

  test('credenciales inválidas muestran error sin navegar', async ({ browser }) => {
    const ctx = await browser.newContext({ storageState: { cookies: [], origins: [] } })
    const page = await ctx.newPage()
    await page.goto('/login')
    await page.getByLabel('Usuario').fill('admin')
    await page.getByLabel('Contraseña').fill('contraseña-mala')
    await page.getByRole('button', { name: 'Iniciar sesión' }).click()
    await expect(page.getByRole('alert')).toContainText('Credenciales inválidas')
    expect(new URL(page.url()).pathname).toBe('/login')
    await ctx.close()
  })

  test('login válido lleva al dashboard y /login redirige de vuelta', async ({ page }) => {
    // La sesión del setup ya está activa: /login debe rebotar a /dashboard.
    await page.goto('/login')
    await page.waitForURL('**/dashboard')
    await expect(page.getByRole('heading', { name: /panel 360/i })).toBeVisible()
  })

  test('logout vuelve a /login', async ({ page }) => {
    await page.goto('/dashboard')
    await page.getByRole('button', { name: /cerrar sesión/i }).click()
    await page.waitForURL('**/login')
  })
})
