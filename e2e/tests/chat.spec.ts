import { expect, test } from '@playwright/test'

// Flujo completo de captura agent-first: enviar una observación en lenguaje
// natural y verificar que el panel de extracción estructurada la muestra
// completa (los campos vienen del ExtractionResult anidado vía
// normalizeExtraction). El LLM (MedPsy en QVAC) procesa en CPU: el stream
// SSE puede tardar ~1 min; los timeouts viven en playwright.config.ts.

test('captura con extracción estructurada visible', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: /captura agent-first/i })).toBeVisible()

  await page.getByLabel(/captura rápida/i).fill(
    'En el Hospital Aurora de Ciudad de Panamá hay 2 resonancias Siemens MAGNETOM Vida de 9 años, modalidad confirmada',
  )
  await page.getByRole('button', { name: /enviar al agente/i }).click()

  // El panel aparece con el evento SSE de extracción.
  await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).toBeVisible()

  // Campos del panel (dt label -> dd valor), estructura dl > div > dt + dd.
  const field = (label: string) =>
    page
      .locator('dl > div')
      .filter({ has: page.locator('dt', { hasText: label }) })
      .locator('dd')
      .first()

  await expect(await field('Instalación').textContent()).toContain('Hospital Aurora')
  await expect(await field('Ciudad').textContent()).toContain('Ciudad de Panamá')
  await expect(await field('Modalidad').textContent()).toContain('MR')
  await expect(await field('Cantidad').textContent()).toContain('2')
  await expect(await field('Fabricante').textContent()).toContain('Siemens')

  const confirm = page.getByRole('button', { name: /confirmar registro/i })
  await expect(confirm).toBeEnabled()
  await confirm.click()
  await expect(page.getByRole('button', { name: /confirmado/i })).toBeVisible()

  // El JSON crudo de extracción nunca debe renderizarse como mensaje visible:
  // el usuario solo ve la card "Extracción estructurada" y el texto del agente.
  await expect(page.locator('body')).not.toContainText('{"facility"')
})
