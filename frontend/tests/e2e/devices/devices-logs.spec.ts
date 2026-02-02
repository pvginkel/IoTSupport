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

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      // Log viewer should not be visible
      await expect(devicesPage.logsViewer).not.toBeVisible();
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

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      // Log viewer should not be visible
      await expect(devicesPage.logsViewer).not.toBeVisible();
    });

    test('log viewer handles Elasticsearch unavailable gracefully', async ({ page, devices }) => {
      // Create a device with entity_id to trigger logs fetching
      const device = await devices.create({
        deviceEntityId: devices.randomDeviceEntityId('es_unavailable_test')
      });

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
    });
  });

  test.describe('Mode restrictions', () => {
    test('log viewer is not present in new device mode', async ({ page, deviceModels }) => {
      const model = await deviceModels.create();

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoNew();
      await devicesPage.waitForEditorLoaded();

      // Select a model
      await devicesPage.selectModel(model.name);

      // Log viewer should not exist in new mode
      await expect(devicesPage.logsViewer).not.toBeVisible();
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
    });
  });
});
