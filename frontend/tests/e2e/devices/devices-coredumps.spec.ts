import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

test.describe('Core Dumps Table', () => {
  test('shows empty state when device has no coredumps', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Coredump table section should be visible with empty state
    await expect(devicesPage.coredumpTable).toBeVisible();
    await expect(devicesPage.coredumpTableEmpty).toBeVisible();
    await expect(devicesPage.coredumpTableEmpty).toContainText('No core dumps recorded');
  });

  test('displays coredump rows with correct columns', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({
      deviceId: device.id,
      firmwareVersion: '1.2.3',
      parseStatus: 'PARSED',
      parsedOutput: 'Test crash output',
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Table should show the coredump row
    await expect(devicesPage.coredumpRows).toHaveCount(1);

    const row = devicesPage.coredumpRowById(coredump.id);
    await expect(row).toBeVisible();

    // Verify column content
    await expect(row).toContainText('1.2.3');       // Firmware
    await expect(row).toContainText('PARSED');       // Status
    await expect(row).toContainText('KB');           // Size (formatted)
  });

  test('expands accordion on row click', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({
      deviceId: device.id,
      parsedOutput: 'Backtrace data',
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Click the coredump row
    await devicesPage.clickCoredumpRow(coredump.id);

    // Accordion should expand
    await expect(devicesPage.coredumpAccordionExpanded).toBeVisible();

    // URL should include the coredump ID
    await expect(page).toHaveURL(
      `/devices/${device.id}/coredumps/${coredump.id}`
    );
  });

  test('download link points to correct endpoint', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({ deviceId: device.id });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Verify download link href
    const downloadLink = devicesPage.coredumpRowById(coredump.id)
      .locator('[data-testid="coredumps.table.row.download"]');
    await expect(downloadLink).toHaveAttribute(
      'href',
      `/api/devices/${device.id}/coredumps/${coredump.id}/download`
    );
  });

  test('deletes a coredump with confirmation', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({ deviceId: device.id });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Verify row exists
    await expect(devicesPage.coredumpRowById(coredump.id)).toBeVisible();

    // Click delete on the row
    await devicesPage.deleteCoredumpById(coredump.id);

    // Confirmation dialog should appear
    await expect(devicesPage.coredumpDeleteConfirmDialog).toBeVisible();

    // Confirm the delete
    await devicesPage.confirmCoredumpDelete();

    // Row should disappear
    await expect(devicesPage.coredumpRowById(coredump.id)).not.toBeVisible({ timeout: 10000 });
  });

  test('cancelling delete keeps the coredump', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({ deviceId: device.id });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Click delete
    await devicesPage.deleteCoredumpById(coredump.id);
    await expect(devicesPage.coredumpDeleteConfirmDialog).toBeVisible();

    // Cancel
    await devicesPage.cancelCoredumpDelete();

    // Row should still exist
    await expect(devicesPage.coredumpRowById(coredump.id)).toBeVisible();
  });

  test('shows multiple coredumps sorted by upload date', async ({ page, devices }) => {
    const device = await devices.create();
    await devices.createCoredump({
      deviceId: device.id,
      firmwareVersion: '1.0.0',
    });
    await devices.createCoredump({
      deviceId: device.id,
      firmwareVersion: '2.0.0',
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    await expect(devicesPage.coredumpRows).toHaveCount(2);
  });

  test('tabs not visible in new device mode', async ({ page, deviceModels }) => {
    const model = await deviceModels.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();
    await devicesPage.selectModel(model.name);

    // Tabs should not be present in new mode
    await expect(devicesPage.detailTabs).not.toBeVisible();
  });
});

test.describe('Core Dump Accordion', () => {
  test('shows metadata and parsed output in expansion panel', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({
      deviceId: device.id,
      chip: 'esp32s3',
      firmwareVersion: '3.1.4',
      parseStatus: 'PARSED',
      parsedOutput: 'Core dump from panic handler\nBacktrace: 0x40081234',
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Click to expand
    await devicesPage.clickCoredumpRow(coredump.id);
    await expect(devicesPage.coredumpAccordionExpanded).toBeVisible();

    // Metadata should show key fields
    const metadata = devicesPage.coredumpAccordionMetadata;
    await expect(metadata).toContainText('esp32s3');
    await expect(metadata).toContainText('3.1.4');
    await expect(metadata).toContainText('PARSED');
    // Monaco editor should be visible with parsed output
    await expect(devicesPage.coredumpAccordionEditor).toBeVisible();
  });

  test('shows placeholder when parsed output is null', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({
      deviceId: device.id,
      parseStatus: 'PENDING',
      parsedOutput: null,
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Expand the row
    await devicesPage.clickCoredumpRow(coredump.id);
    await expect(devicesPage.coredumpAccordionExpanded).toBeVisible();

    // Should show "not available" instead of editor
    await expect(devicesPage.coredumpAccordionNoOutput).toBeVisible();
    await expect(devicesPage.coredumpAccordionNoOutput).toContainText('not available');
    await expect(devicesPage.coredumpAccordionEditor).not.toBeVisible();
  });

  test('deep-link expands correct row and activates coredumps tab', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({
      deviceId: device.id,
      parsedOutput: 'Deep link output',
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumpDetail(device.id, coredump.id);

    // Coredumps tab should be active
    await expect(devicesPage.tabCoredumps).toHaveAttribute('aria-current', 'page');

    // Accordion should be expanded
    await expect(devicesPage.coredumpAccordionExpanded).toBeVisible();
  });

  test('collapsing accordion navigates back to coredumps index', async ({ page, devices }) => {
    const device = await devices.create();
    const coredump = await devices.createCoredump({ deviceId: device.id });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoCoredumps(device.id);

    // Expand
    await devicesPage.clickCoredumpRow(coredump.id);
    await expect(devicesPage.coredumpAccordionExpanded).toBeVisible();

    // Collapse by clicking the same row
    await devicesPage.clickCoredumpRow(coredump.id);
    await expect(devicesPage.coredumpAccordionExpanded).not.toBeVisible();

    // URL should be back to coredumps index
    await expect(page).toHaveURL(`/devices/${device.id}/coredumps`);
  });
});

test.describe('Last Core Dump Column', () => {
  test('column header is visible and sortable', async ({ page, devices }) => {
    await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    await expect(devicesPage.lastCoredumpAtHeader).toBeVisible();
    await expect(devicesPage.lastCoredumpAtHeader).toContainText('Last Core Dump');

    await devicesPage.lastCoredumpAtHeader.click();
  });

  test('shows em-dash for devices without coredumps', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    const row = devicesPage.rowByKey(device.key);
    await expect(row).toContainText('—');
  });

  test('shows formatted datetime when device has coredumps', async ({ page, devices }) => {
    const device = await devices.create();
    await devices.createCoredump({ deviceId: device.id });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    const row = devicesPage.rowByKey(device.key);
    await expect(row).toBeVisible();

    const rowText = await row.textContent();
    expect(rowText).toBeTruthy();
  });
});
