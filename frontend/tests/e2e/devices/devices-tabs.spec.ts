import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

test.describe('Device Tab Navigation', () => {
  test('configuration tab is active by default', async ({ page, devices }) => {
    const device = await devices.create();

    // Clear any stored tab preference so the default (edit) applies
    await page.goto('/devices');
    await page.evaluate(() => localStorage.removeItem('iot-support-device-tab'));

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);

    // Bare route should redirect to /edit and show the configuration tab
    await expect(page).toHaveURL(`/devices/${device.id}/edit`);
    await devicesPage.waitForEditorLoaded();
    await expect(devicesPage.tabConfiguration).toHaveAttribute('aria-current', 'page');
  });

  test('tab navigation changes URL correctly', async ({ page, devices }) => {
    const device = await devices.create();

    // Clear any stored tab preference so we start on configuration
    await page.goto('/devices');
    await page.evaluate(() => localStorage.removeItem('iot-support-device-tab'));

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
    await expect(page).toHaveURL(`/devices/${device.id}/edit`);
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

    // Direct navigate to configuration/edit tab
    await page.goto(`/devices/${device.id}/edit`);
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

test.describe('Device Tab Persistence', () => {
  test('logs tab preference persists across device navigation', async ({ page, devices }) => {
    const deviceA = await devices.create({ deviceName: 'Tab Persist A' });
    const deviceB = await devices.create({ deviceName: 'Tab Persist B' });

    // Clear any stored tab preference
    await page.goto('/devices');
    await page.evaluate(() => localStorage.removeItem('iot-support-device-tab'));

    const devicesPage = new DevicesPage(page);

    // Open device A and navigate to the Logs tab
    await devicesPage.gotoEdit(deviceA.id);
    await devicesPage.waitForEditorLoaded();
    await devicesPage.clickTab('logs');
    await expect(page).toHaveURL(`/devices/${deviceA.id}/logs`);
    await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');

    // Navigate back to device list and open device B
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();
    await devicesPage.editDeviceById(deviceB.id);

    // The Logs tab should be active on device B because the preference persisted
    await expect(page).toHaveURL(`/devices/${deviceB.id}/logs`);
    await expect(devicesPage.tabLogs).toHaveAttribute('aria-current', 'page');
  });

  test('coredumps tab preference persists across device navigation', async ({ page, devices }) => {
    const deviceA = await devices.create({ deviceName: 'Tab Persist C' });
    const deviceB = await devices.create({ deviceName: 'Tab Persist D' });

    // Clear any stored tab preference
    await page.goto('/devices');
    await page.evaluate(() => localStorage.removeItem('iot-support-device-tab'));

    const devicesPage = new DevicesPage(page);

    // Open device A and navigate to the Core Dumps tab
    await devicesPage.gotoEdit(deviceA.id);
    await devicesPage.waitForEditorLoaded();
    await devicesPage.clickTab('coredumps');
    await expect(page).toHaveURL(`/devices/${deviceA.id}/coredumps`);
    await expect(devicesPage.tabCoredumps).toHaveAttribute('aria-current', 'page');

    // Navigate back to device list and open device B
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();
    await devicesPage.editDeviceById(deviceB.id);

    // The Core Dumps tab should be active on device B because the preference persisted
    await expect(page).toHaveURL(`/devices/${deviceB.id}/coredumps`);
    await expect(devicesPage.tabCoredumps).toHaveAttribute('aria-current', 'page');
  });
});
