import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

test.describe('Device Logs Tab', () => {
  test.describe('Visibility based on entity_id', () => {
    test('shows empty state when device has no entity_id', async ({ page, devices }) => {
      const device = await devices.create({
        config: {
          deviceName: 'Test Device No Entity',
          deviceEntityId: '',
          enableOTA: false
        }
      });

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);

      // Empty state should be visible on the logs tab
      await expect(devicesPage.logsEmptyState).toBeVisible();
      await expect(devicesPage.logsEmptyState).toContainText('No entity ID configured');
    });

    test('shows empty state when device has null entity_id', async ({ page, devices }) => {
      const device = await devices.create({
        config: {
          deviceName: 'Test Device Null Entity',
          enableOTA: false
        }
      });

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);

      // Empty state should be visible
      await expect(devicesPage.logsEmptyState).toBeVisible();
    });

    test('log viewer is always visible when entity_id exists', async ({ page, devices }) => {
      const device = await devices.create({
        deviceEntityId: devices.randomDeviceEntityId('viewer_visible_test')
      });

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);

      // Wait for the logs API request to complete (success or failure)
      await page.waitForResponse(
        response => response.url().includes(`/api/devices/${device.id}/logs`),
        { timeout: 10000 }
      ).catch(() => {
        // Request may have already completed or ES may be unavailable
      });

      // The viewer should always be visible (even with no logs or ES unavailable)
      await expect(devicesPage.logsViewer).toBeVisible();
      await expect(devicesPage.detailHeader).toBeVisible();
      await expect(devicesPage.detailTabs).toBeVisible();
    });
  });

  test.describe('Mode restrictions', () => {
    test('tabs are not visible in new device mode', async ({ page, deviceModels }) => {
      const model = await deviceModels.create();

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoNew();
      await devicesPage.waitForEditorLoaded();

      await devicesPage.selectModel(model.name);

      // Tabs should not exist in new mode
      await expect(devicesPage.detailTabs).not.toBeVisible();
    });

    test('tabs are not visible in duplicate mode', async ({ page, devices }) => {
      const sourceDevice = await devices.create({
        config: {
          deviceName: 'Source Device',
          deviceEntityId: '',
          enableOTA: false
        }
      });

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoDuplicate(sourceDevice.id);
      await devicesPage.waitForEditorLoaded();

      // Tabs should not be visible in duplicate mode
      await expect(devicesPage.detailTabs).not.toBeVisible();
    });
  });
});
