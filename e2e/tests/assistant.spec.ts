import { expect, test } from '@playwright/test'

// Asistente agentic (Fase 5): una pregunta general (sin datos de campo)
// clasifica como "question" y responde vía tool loop: burbuja normal de
// assistant (data-testid="assistant-answer"), sin card de extracción y sin
// JSON crudo en el DOM. MedPsy procesa en CPU: timeouts en playwright.config.ts.

test('pregunta general: burbuja de respuesta del asistente', async ({ page }) => {
  await page.goto('/chat')
  await expect(page.getByRole('heading', { name: /captura agent-first/i })).toBeVisible()

  await page.getByLabel(/captura rápida/i).fill('¿Qué equipos hay?')
  await page.getByRole('button', { name: /enviar al agente/i }).click()

  // El asistente consulta el grafo (chips de tool) y termina con una burbuja
  // de respuesta normal, no con una card de extracción.
  const answer = page.getByTestId('assistant-answer')
  await expect(answer).toBeVisible()
  await expect(answer).not.toBeEmpty()

  // La pregunta no genera card de extracción estructurada.
  await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).toHaveCount(0)

  // JSON crudo del tool loop (acciones/args) nunca se renderiza como texto.
  await expect(page.locator('body')).not.toContainText('{"action"')
  await expect(page.locator('body')).not.toContainText('{"facility"')
})

test('sugerencias de preguntas rellenan la captura', async ({ page }) => {
  await page.goto('/chat')

  // Con el panel vacío aparecen chips de preguntas de ejemplo.
  const suggestion = page.getByRole('button', { name: /cuántas resonancias hay en valencia/i })
  await expect(suggestion).toBeVisible()
  await suggestion.click()

  const capture = page.getByLabel(/captura rápida/i)
  await expect(capture).toHaveValue(/cuántas resonancias hay en valencia/i)
})
