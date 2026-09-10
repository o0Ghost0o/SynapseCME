import { expect, test } from '@playwright/test'

// Sesiones de chat múltiples (Fase 4): cada mensaje crea/continúa una
// conversación server-side; el backend genera el título fire-and-forget
// (MedPsy en CPU, puede tardar) y el frontend lo muestra al refrescar la
// lista tras el evento SSE `done`. Estos tests asumen el stack desplegado
// con los endpoints /api/conversations activos.

test.use({ viewport: { width: 1280, height: 800 } })

async function titledConversations(page: import('@playwright/test').Page): Promise<string[]> {
  const texts = await page.getByTestId('conversation-item').allInnerTexts()
  return texts.map((t) => t.replace(/\s+/g, ' ').trim())
}

test.describe('sesiones de chat', () => {
  test('crear conversación: aparece en la lista con título generado', async ({ page }) => {
    await page.goto('/chat')
    await expect(page.getByRole('heading', { name: /captura agent-first/i })).toBeVisible()

    const before = await page.getByTestId('conversation-item').count()

    await page.getByLabel(/captura rápida/i).fill(
      'En el Hospital Prueba E2E hay 1 tomógrafo GE LightSpeed de 4 años',
    )
    await page.getByRole('button', { name: /enviar al agente/i }).click()

    // El pipeline responde y el done ancla la conversación (lista refrescada).
    await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).toBeVisible()
    await expect
      .poll(async () => page.getByTestId('conversation-item').count(), {
        timeout: 120_000,
        intervals: [2_000, 5_000],
      })
      .toBeGreaterThan(before)

    // El título llega después (fire-and-forget): algún ítem distinto de
    // «Nueva conversación» debe aparecer.
    await expect
      .poll(async () => (await titledConversations(page)).some((t) => !t.includes('Nueva conversación')), {
        timeout: 300_000,
        intervals: [5_000, 10_000],
      })
      .toBe(true)
  })

  test('segunda conversación: ambas en la lista y el historial se carga al click', async ({ page }) => {
    await page.goto('/chat')
    const before = await page.getByTestId('conversation-item').count()

    // Primera conversación: marcas únicas para identificar su historial. La
    // anclamos por id (data-cid): la lista se reordena por actividad y los
    // títulos los genera el modelo, así que la posición no es estable.
    const marker1 = `Hospital Marcador Uno ${Date.now()}`
    await page.getByLabel(/captura rápida/i).fill(`En el ${marker1} hay 1 resonancia Siemens de 5 años`)
    await page.getByRole('button', { name: /enviar al agente/i }).click()
    await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).toBeVisible()
    // La card aparece antes de que el SSE `done` refresque la lista: esperar
    // a que la nueva conversación entre en la lista antes de tomar su id.
    await expect
      .poll(async () => page.getByTestId('conversation-item').count(), {
        timeout: 120_000,
        intervals: [2_000, 5_000],
      })
      .toBeGreaterThan(before)
    const firstCid = await page.getByTestId('conversation-item').nth(0).getAttribute('data-cid')
    expect(firstCid).toBeTruthy()

    // Segunda conversación (botón Nueva reinicia el panel).
    await page.getByTestId('new-conversation').click()
    await expect(page.getByText(/ejemplo:/i)).toBeVisible()
    const marker2 = `Hospital Marcador Dos ${Date.now()}`
    await page.getByLabel(/captura rápida/i).fill(`En el ${marker2} hay 1 ecógrafo Philips de 2 años`)
    await page.getByRole('button', { name: /enviar al agente/i }).click()
    await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).toBeVisible()

    // Ambas conversaciones tituladas en la lista.
    await expect
      .poll(
        async () => {
          const titles = (await titledConversations(page)).filter((t) => !t.includes('Nueva conversación'))
          return titles.length
        },
        { timeout: 300_000, intervals: [5_000, 10_000] },
      )
      .toBeGreaterThanOrEqual(2)

    // Click en la primera conversación por id: el historial se carga con su
    // mensaje y la card reconstruida; el registro histórico no admite
    // re-confirmación.
    await page.locator(`[data-cid="${firstCid}"]`).click()
    await expect(page.getByText(marker1)).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Extracción estructurada' })).toBeVisible()
    const historyConfirm = page.getByRole('button', { name: /registro histórico|confirmar registro/i })
    await expect(historyConfirm.first()).toBeDisabled()
  })
})
