import { expect, test } from '@playwright/test'

// Smoke de las vistas principales con sesión activa (storageState del setup).
test.describe('vistas principales', () => {
  test('dashboard 360 carga', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: /panel 360/i })).toBeVisible()
  })

  test('chat carga listo para preguntar o dictar', async ({ page }) => {
    await page.goto('/chat')
    await expect(page.getByRole('heading', { name: /captura agent-first/i })).toBeVisible()
    await expect(page.getByText(/pregunta o dicta una observación/i)).toBeVisible()
  })

  test('métricas del modelo carga', async ({ page }) => {
    await page.goto('/metricas')
    await expect(page.getByRole('heading', { name: /métricas del modelo/i })).toBeVisible()
  })

  test('red en vivo carga', async ({ page }) => {
    await page.goto('/network')
    await expect(page.getByRole('heading', { name: /red en vivo/i })).toBeVisible()
  })

  test('red en vivo: nodo principal muestra qué está corriendo', async ({ page }) => {
    await page.goto('/network')
    await expect(page.getByRole('heading', { name: /nodo principal/i })).toBeVisible()

    // El núcleo reporta el estado de QVAC, STT y el grafo. (El panel se
    // renderiza dos veces — overlay desktop + fallback móvil —: se toma el primero.)
    await expect(page.getByText(/inferencia qvac/i).first()).toBeVisible()
    await expect(page.getByText('medpsy:q4_k_m', { exact: true }).first()).toBeVisible()
    await expect(page.getByText(/EMBEDDINGGEMMA/i).first()).toBeVisible()
    await expect(page.getByText(/faster-whisper/i).first()).toBeVisible()
    await expect(page.getByText(/instalaciones/i).first()).toBeVisible()

    // El nodo principal está inyectado en el grafo (title nativo del nodo).
    const canvas = page.locator('svg[aria-label="Grafo de red de instalaciones"]')
    await expect(canvas).toBeVisible()
    const coreTitle = canvas.locator('title', { hasText: 'Synapse Core' })
    await expect(coreTitle).toHaveCount(1)

    // Hover sobre el nodo: el tooltip sigue al cursor con su nombre.
    const coreGroup = coreTitle.locator('xpath=..')
    await coreGroup.locator('circle').last().hover()
    await expect(canvas.locator('text.fill-white')).toContainText('Synapse Core')
  })

  test('admin de usuarios carga (rol admin)', async ({ page }) => {
    await page.goto('/admin')
    await expect(page).toHaveURL(/\/admin/)
  })

  test('menú hamburguesa en móvil despliega la navegación', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: /panel 360/i })).toBeVisible()

    // En móvil no hay enlaces inline: el hamburger concentra la navegación.
    const menu = page.getByTestId('nav-menu')
    await expect(menu).toBeHidden()
    await page.getByTestId('nav-menu-button').click()
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('link', { name: 'Métricas' })).toBeVisible()

    // Navegar desde el menú cierra el panel y cambia de vista.
    await menu.getByRole('link', { name: 'Métricas' }).click()
    await expect(page).toHaveURL(/\/metricas/)
    await expect(menu).toBeHidden()
    await expect(page.getByRole('heading', { name: /métricas del modelo/i })).toBeVisible()
  })
})
