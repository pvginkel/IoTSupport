import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

test.describe('Device Tab Navigation', () => {
  test('configuration tab is active by default', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Configuration tab should be active
    await expect(devicesPage.tabConfiguration).toHaveAttribute('aria-current', 'page');
  });

  test('tab navigation changes URL correctly', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Navigate to Logs tab
    await devicesPage.clickTab('logs');
    await expect(page).toHaveURL(`/devices/${device.id}/logs`);
    await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');

    // Navigate to Core Dumps tab
    await devicesPage.clickTab('coredumps');
    await expect(page).toHaveURL(`/devices/${device.id}/coredumps`);
    await expect(devicesPage.tabCoredumps).toHaveAttribute('aria-current', 'page');

    // Navigate back to Configuration tab
    await devicesPage.clickTab('configuration');
    await expect(page).toHaveURL(`/devices/${device.id}`);
    await expect(devicesPage.tabConfiguration).toHaveAttribute('aria-current', 'page');
  });

  test('tabs are hidden in new device mode', async ({ page, deviceModels }) => {
    const model = await deviceModels.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();
    await devicesPage.selectModel(model.name);

    await expect(devicesPage.detailTabs).not.toBeVisible();
    await expect(devicesPage.detailHeader).not.toBeVisible();
  });

  test('tabs are hidden in duplicate mode', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoDuplicate(device.id);
    await devicesPage.waitForEditorLoaded();

    await expect(devicesPage.detailTabs).not.toBeVisible();
    await expect(devicesPage.detailHeader).not.toBeVisible();
  });

  test('deep-links work for all three tabs', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);

    // Direct navigate to logs tab
    await devicesPage.gotoLogs(device.id);
    await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');

    // Direct navigate to coredumps tab
    await devicesPage.gotoCoredumps(device.id);
    await expect(devicesPage.tabCoredumps).toHaveAttribute('aria-current', 'page');

    // Direct navigate to configuration tab (index)
    await devicesPage.gotoEdit(device.id);
    await expect(devicesPage.tabConfiguration).toHaveAttribute('aria-current', 'page');
  });

  test('core dumps tab badge shows count', async ({ page, devices }) => {
    const device = await devices.create();
    await devices.createCoredump({ deviceId: device.id });
    await devices.createCoredump({ deviceId: device.id });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // The coredumps tab should contain a badge with the count
    await expect(devicesPage.tabCoredumps).toContainText('2');
  });

  test('header shows device key, model, rotation badge, OTA status', async ({ page, devices }) => {
    const device = await devices.create({
      enableOta: true,
      deviceName: 'Tab Test Device'
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Header should display device identity info
    await expect(devicesPage.headerDeviceKey).toContainText(device.key);
    await expect(devicesPage.headerDeviceModel).toBeVisible();
    await expect(devicesPage.headerRotationBadge).toBeVisible();
    await expect(devicesPage.headerOtaBadge).toContainText('Enabled');
  });
});
