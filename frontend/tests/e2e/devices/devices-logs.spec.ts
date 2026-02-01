import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

test.describe('Device Logs Viewer', () => {
  test.describe('Visibility based on entity_id', () => {
    test('log viewer is hidden when device has no entity_id', async ({ page, devices }) => {
      // Create a device without entity_id
      const device = await devices.create({
        config: {
          deviceName: 'Test Device No Entity',
          deviceEntityId: '', // Empty entity_id
          enableOTA: false
        }
      });

      try {
        const devicesPage = new DevicesPage(page);
        await devicesPage.gotoEdit(device.id);
        await devicesPage.waitForEditorLoaded();

        // Log viewer should not be visible
        await expect(devicesPage.logsViewer).not.toBeVisible();
      } finally {
        await devices.delete(device.id);
      }
    });

    test('log viewer is hidden when device has null entity_id', async ({ page, devices }) => {
      // Create a device with config that doesn't include deviceEntityId
      const device = await devices.create({
        config: {
          deviceName: 'Test Device Null Entity',
          enableOTA: false
          // deviceEntityId intentionally omitted
        }
      });

      try {
        const devicesPage = new DevicesPage(page);
        await devicesPage.gotoEdit(device.id);
        await devicesPage.waitForEditorLoaded();

        // Log viewer should not be visible
        await expect(devicesPage.logsViewer).not.toBeVisible();
      } finally {
        await devices.delete(device.id);
      }
    });

    test('log viewer handles Elasticsearch unavailable gracefully', async ({ page, devices }) => {
      // Create a device with entity_id to trigger logs fetching
      const device = await devices.create({
        deviceEntityId: devices.randomDeviceEntityId('es_unavailable_test')
      });

      try {
        const devicesPage = new DevicesPage(page);
        await devicesPage.gotoEdit(device.id);
        await devicesPage.waitForEditorLoaded();

        // Wait for the logs API request to complete (success or failure)
        // Using waitForResponse is deterministic - no fixed timeout needed
        await page.waitForResponse(
          response => response.url().includes(`/api/devices/${device.id}/logs`),
          { timeout: 10000 }
        ).catch(() => {
          // Request may have already completed before we started waiting,
          // or ES may be unavailable - both are acceptable for this test
        });

        // The viewer should be hidden (no logs due to ES unavailable)
        // and no error UI should be shown (silent error handling)
        // The page should remain functional
        await expect(devicesPage.editor).toBeVisible();

        // The JSON editor should still work
        await expect(devicesPage.jsonEditorContainer).toBeVisible();

        // Log viewer should not be visible when ES returns no logs or errors
        await expect(devicesPage.logsViewer).not.toBeVisible();
      } finally {
        await devices.delete(device.id);
      }
    });
  });

  test.describe('Mode restrictions', () => {
    test('log viewer is not present in new device mode', async ({ page, deviceModels }) => {
      const model = await deviceModels.create();

      try {
        const devicesPage = new DevicesPage(page);
        await devicesPage.gotoNew();
        await devicesPage.waitForEditorLoaded();

        // Select a model
        await devicesPage.selectModel(model.name);

        // Log viewer should not exist in new mode
        await expect(devicesPage.logsViewer).not.toBeVisible();
      } finally {
        await deviceModels.delete(model.id);
      }
    });

    test('log viewer is not present in duplicate mode', async ({ page, devices }) => {
      // Create a source device without entity_id to avoid triggering logs fetch
      const sourceDevice = await devices.create({
        config: {
          deviceName: 'Source Device',
          deviceEntityId: '', // No entity_id to avoid ES call
          enableOTA: false
        }
      });

      try {
        const devicesPage = new DevicesPage(page);
        await devicesPage.gotoEdit(sourceDevice.id);
        await devicesPage.waitForEditorLoaded();

        // Click duplicate button
        await devicesPage.duplicate();

        // Should navigate to duplicate mode
        await expect(page).toHaveURL(/\/devices\/new\?/);
        await devicesPage.waitForEditorLoaded();

        // Log viewer should not be visible in duplicate mode
        await expect(devicesPage.logsViewer).not.toBeVisible();
      } finally {
        try { await devices.delete(sourceDevice.id); } catch { /* ignore */ }
      }
    });
  });
});

/**
 * Note: The following tests require a working Elasticsearch backend with the
 * log seeding endpoint (/api/testing/devices/{device_id}/logs).
 *
 * These tests are commented out until the backend testing endpoint is available:
 * - live updates checkbox is checked by default when viewer is visible
 * - checkbox can be toggled off and on
 * - scroll-at-bottom attribute is set correctly
 * - auto-scroll behavior when new logs arrive
 *
 * To enable these tests:
 * 1. Ensure the backend provides POST /api/testing/devices/{device_id}/logs
 * 2. Add a seedLogs method to the DevicesFactory
 * 3. Uncomment and update the tests below
 */

// test.describe('Checkbox toggle (requires ES)', () => {
//   test('live updates checkbox is checked by default when viewer is visible', async ({ page, devices }) => {
//     const device = await devices.create({
//       deviceEntityId: devices.randomDeviceEntityId('checkbox_test')
//     });
//
//     try {
//       // Seed logs to ensure viewer is visible
//       // await devices.seedLogs(device.id, ['Log message 1', 'Log message 2']);
//
//       const devicesPage = new DevicesPage(page);
//       await devicesPage.gotoEdit(device.id);
//       await devicesPage.waitForEditorLoaded();
//
//       await expect(devicesPage.logsViewer).toBeVisible();
//       await expect(devicesPage.logsLiveCheckbox).toBeChecked();
//     } finally {
//       await devices.delete(device.id);
//     }
//   });
// });
