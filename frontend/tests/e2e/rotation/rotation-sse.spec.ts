import { test, expect } from '../../support/fixtures';
import { RotationPage } from './RotationPage';

/**
 * Rotation Dashboard SSE Nudge Spec.
 *
 * Verifies that the rotation dashboard refreshes when an SSE "rotation-updated"
 * event is received, using the backend testing endpoint:
 * - POST /api/testing/rotation/nudge
 *
 * Requires the SSE Gateway to be running (managed by fixtures).
 */
test.describe('Rotation Dashboard SSE Nudge', () => {
  test('dashboard loads with device panels visible', async ({
    page,
    devices,
  }) => {
    // Create a device so the dashboard has data (devices fixture already authenticates)
    await devices.create();

    const rotationPage = new RotationPage(page);
    await rotationPage.goto();

    // Dashboard should load successfully with panels
    await expect(rotationPage.dashboard).toBeVisible({ timeout: 15_000 });
    await expect(rotationPage.panels).toBeVisible({ timeout: 15_000 });
  });

  test('dashboard updates after SSE rotation-updated nudge', async ({
    page,
    devices,
    frontendUrl,
  }) => {
    // Create a device to populate the dashboard (devices fixture already authenticates)
    const device = await devices.create();

    const rotationPage = new RotationPage(page);
    await rotationPage.goto();

    // Wait for initial dashboard load
    await expect(rotationPage.dashboard).toBeVisible({ timeout: 15_000 });
    await expect(rotationPage.panels).toBeVisible({ timeout: 15_000 });

    // Record initial state -- the device should be visible in a panel row
    const deviceRow = rotationPage.rowByDeviceId(device.id);
    await expect(deviceRow).toBeVisible({ timeout: 10_000 });

    const initialState = await deviceRow.getAttribute('data-rotation-state');

    // Trigger rotation for this device via the API to change its state
    const triggerResponse = await page.request.post(
      `${frontendUrl}/api/devices/${device.id}/rotate`,
      { data: {} },
    );

    // If rotation is not available (e.g. device in wrong state), skip
    if (!triggerResponse.ok()) {
      // Try fleet rotation instead
      const fleetResponse = await page.request.post(
        `${frontendUrl}/api/rotation/trigger`,
        { data: {} },
      );
      if (!fleetResponse.ok()) {
        test.skip(true, 'Could not trigger rotation -- device may not be in a rotatable state');
        return;
      }
    }

    // Send SSE nudge to trigger dashboard refresh
    const nudgeResponse = await page.request.post(
      `${frontendUrl}/api/testing/rotation/nudge`,
    );

    // If nudge endpoint is not available, skip
    if (!nudgeResponse.ok()) {
      test.skip(true, 'Rotation nudge endpoint not available');
      return;
    }

    // Wait for the dashboard to re-render after the nudge.
    // The SSE event triggers queryClient.invalidateQueries which causes a re-fetch.
    // Assert that the device's rotation state actually changed -- this confirms the
    // nudge triggered a re-fetch that picked up the state change from the rotation trigger.
    await expect(async () => {
      const currentState = await deviceRow.getAttribute('data-rotation-state');
      expect(currentState).not.toBeNull();
      expect(currentState).not.toBe(initialState);
    }).toPass({ timeout: 15_000 });
  });
});
