import { expect, test } from '@playwright/test'

// Smoke de las vistas principales con sesión activa (storageState del setup).
test.describe('vistas principales', () => {
  test('dashboard 360 carga', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: /panel 360/i })).toBeVisible()
  })

  test('chat carga en modo app de campo', async ({ page }) => {
    await page.goto('/chat')
    await expect(page.getByRole('heading', { name: /captura agent-first/i })).toBeVisible()
    await expect(page.getByText(/modo: app de campo/i)).toBeVisible()
  })

  test('métricas del modelo carga', async ({ page }) => {
    await page.goto('/metricas')
    await expect(page.getByRole('heading', { name: /métricas del modelo/i })).toBeVisible()
  })

  test('red en vivo carga', async ({ page }) => {
    await page.goto('/network')
    await expect(page.getByRole('heading', { name: /red en vivo/i })).toBeVisible()
  })

  test('admin de usuarios carga (rol admin)', async ({ page }) => {
    await page.goto('/admin')
    await expect(page).toHaveURL(/\/admin/)
  })
})
