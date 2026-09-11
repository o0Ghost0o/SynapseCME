import { expect, test } from '@playwright/test'

// Detalle de equipo (3a) y filtros del dashboard (3b). Las instalaciones seed
// incluyen "Hospital Aurora" (Ciudad de Panamá) con equipos MR/CT/RF/US/MG.

async function openHospitalAurora(page: import('@playwright/test').Page) {
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name: /panel 360/i })).toBeVisible()
  // Expandir todas las regiones y países (el árbol arranca colapsado) hasta
  // poder clicar la instalación, esté en la región que esté.
  for (const btn of await page.getByTestId('tree-region').all()) await btn.click()
  for (const btn of await page.getByTestId('tree-country').all()) await btn.click()
  await page.getByTestId('tree-facility').filter({ hasText: 'Hospital Aurora' }).first().click()
  await expect(page.getByRole('heading', { name: 'Hospital Aurora' })).toBeVisible()
}

test.describe('detalle de equipo', () => {
  test('click en equipo navega a /equipos/[id] y muestra fabricante/modelo', async ({ page }) => {
    await openHospitalAurora(page)

    const item = page.getByTestId('equipment-item').first()
    await expect(item).toBeVisible()
    const name = ((await item.locator('p').first().textContent()) ?? '').trim()
    expect(name.length).toBeGreaterThan(0)

    await item.click()
    await expect(page).toHaveURL(/\/equipos\//)

    // El header muestra fabricante/modelo y las secciones estructurales existen
    // aunque el equipo no tenga parámetros ni observaciones.
    await expect(page.locator('h1')).toContainText(name.split(' ')[0])
    await expect(page.getByRole('heading', { name: 'Parámetros' })).toBeVisible()
    await expect(page.getByRole('heading', { name: /historial de observaciones/i })).toBeVisible()
  })

  test('equipo inexistente muestra estado 404 sin crashear', async ({ page }) => {
    await page.goto('/equipos/equipo-que-no-existe')
    await expect(page.getByText(/equipo no encontrado/i)).toBeVisible()
  })

  test('mini-chat de revisión: el agente anota la observación en la ficha', async ({ page }) => {
    await openHospitalAurora(page)

    await page.getByTestId('equipment-item').first().click()
    await expect(page).toHaveURL(/\/equipos\//)
    await expect(page.getByTestId('equipment-chat')).toBeVisible()

    const marker = `Revisión E2E corriente ${Date.now()}`
    await page.getByTestId('equipment-chat-input').fill(`${marker}: 10 mA nominal`)
    await page.getByRole('button', { name: /enviar/i }).click()

    // Burbuja del asistente con la confirmación (MedPsy tarda unos segundos).
    const answer = page.getByTestId('equipment-chat-answer')
    await expect(answer).toBeVisible()
    await expect(answer).not.toBeEmpty()

    // Al terminar, la ficha se recarga y la observación queda en el historial.
    await expect(page.getByText(new RegExp(marker)).first()).toBeVisible()
  })
})

test.describe('filtros del dashboard', () => {
  test('filtrar por modalidad MR deja solo cards MR visibles', async ({ page }) => {
    await openHospitalAurora(page)
    await expect(page.getByTestId('equipment-item').first()).toBeVisible()

    await page.getByLabel(/modalidad/i).selectOption('MR')

    const cards = page.getByTestId('modality-card')
    await expect(cards).toHaveCount(1)
    await expect(cards.first().locator('h3')).toHaveText('MR')
    await expect(page.getByTestId('equipment-item').first()).toBeVisible()
    // Al limpiar, el filtro vuelve a "Todas" y la card MR sigue visible
    // (los datos vivos de esta instalación pueden tener una sola modalidad).
    await page.getByRole('button', { name: /limpiar filtros/i }).click()
    await expect(page.getByLabel(/modalidad/i)).toHaveValue('')
    // Tras limpiar vuelven todas las modalidades: la card MR sigue presente
    // (no necesariamente primero — el orden depende de los datos seed).
    await expect(
      cards.filter({ has: page.locator('h3', { hasText: 'MR' }) }).first(),
    ).toBeVisible()
    expect(await cards.count()).toBeGreaterThanOrEqual(1)
  })

  test('ver todos los equipos lista resultados globales agrupados por modalidad', async ({ page }) => {
    await openHospitalAurora(page)

    await page.getByRole('button', { name: /ver todos los equipos/i }).click()
    await expect(page.getByText(/equipos \(global\)/)).toBeVisible()
    await expect(page.getByTestId('equipment-item').first()).toBeVisible()
    // Cada ítem global muestra su instalación.
    await expect(page.getByTestId('equipment-item').first().locator('p').nth(1)).not.toBeEmpty()
  })
})
