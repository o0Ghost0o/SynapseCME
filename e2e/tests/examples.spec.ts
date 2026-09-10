import { expect, test } from '@playwright/test'

// El botón "Ejemplos" abre un dialog con observaciones listas para pegar:
// al hacer click en un ejemplo, el texto queda en el textarea de captura
// SIN enviarse (el usuario decide cuándo enviarlo).

test('ejemplos: click pega el texto en la captura sin enviar', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: /captura agent-first/i })).toBeVisible()

  await page.getByRole('button', { name: /ejemplos/i }).click()

  const dialog = page.getByRole('dialog', { name: /ejemplos de captura/i })
  await expect(dialog).toBeVisible()

  // Filtrar por categoría Resonancia (chip) y elegir el primer ejemplo.
  await dialog.locator('button.glass-chip', { hasText: 'Resonancia' }).click()
  const exampleCard = dialog.locator('ul li button').first()
  const exampleText = (await exampleCard.locator('p').last().textContent()) ?? ''
  expect(exampleText.length).toBeGreaterThan(10)
  await exampleCard.click()

  // El dialog se cierra y el textarea contiene el texto, sin enviarse.
  await expect(dialog).not.toBeVisible()
  const textarea = page.getByLabel(/captura rápida/i)
  await expect(textarea).toHaveValue(exampleText)

  // No aparece burbuja de mensaje enviado ni panel de extracción.
  await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).not.toBeVisible()
  await expect(page.getByRole('button', { name: /procesando/i })).not.toBeVisible()
})
