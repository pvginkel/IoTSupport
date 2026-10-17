/**
 * Stage indicator tests
 *
 * The top bar shows the deployment stage from GET /api/ui-setup, and hides it
 * on prd. Playwright's backends run under FLASK_ENV=testing, so the stage is
 * never prd here: local-tst, unless the backend's environment sets STAGE.
 * Requires use_app_shell=true (excluded when use_app_shell=false).
 */

import { test, expect } from '../../support/fixtures'

test.describe('Stage indicator', () => {
  test('shows the backend stage in the top bar', async ({ page, backendUrl }) => {
    const response = await page.request.get(`${backendUrl}/api/ui-setup`)
    expect(response.ok()).toBe(true)
    const { stage } = (await response.json()) as { stage: string }
    expect(stage).not.toBe('prd')

    await page.goto('/')

    await expect(page.getByTestId('app-shell.topbar.stage-indicator')).toHaveText(stage.toUpperCase())
  })
})
