import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

/**
 * Seed deterministic log entries via the testing endpoint.
 * Returns the seed response (seeded count and window).
 */
async function seedLogs(
  page: import('@playwright/test').Page,
  frontendUrl: string,
  deviceEntityId: string,
  count: number,
): Promise<{ seeded: number; window_start: string; window_end: string }> {
  const resp = await page.request.post(`${frontendUrl}/api/testing/devices/logs/seed`, {
    data: { device_entity_id: deviceEntityId, count },
  });
  expect(resp.ok()).toBe(true);
  return resp.json();
}

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

  test.describe('Backfill on scroll to top', () => {
    test('loads older entries when scrolled to top', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('backfill_test');
      const device = await devices.create({ deviceEntityId: entityId });

      // Seed 1500 entries — initial fetch returns up to 1000, leaving 500 for backfill
      await seedLogs(page, frontendUrl, entityId, 1500);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);

      // Wait for initial load to complete
      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });
      await expect(async () => {
        const count = await devicesPage.getLogsLogCount();
        expect(count).toBeGreaterThan(0);
      }).toPass({ timeout: 10_000 });

      const initialCount = await devicesPage.getLogsLogCount();

      // Scroll to top to trigger backfill
      await devicesPage.scrollLogsToTop();

      // Wait for backfill to increase the log count
      await expect(async () => {
        const count = await devicesPage.getLogsLogCount();
        expect(count).toBeGreaterThan(initialCount);
      }).toPass({ timeout: 10_000 });
    });

    test('preserves scroll position after backfill', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('backfill_scroll_test');
      const device = await devices.create({ deviceEntityId: entityId });

      await seedLogs(page, frontendUrl, entityId, 1500);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);

      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });
      await expect(async () => {
        const count = await devicesPage.getLogsLogCount();
        expect(count).toBeGreaterThan(0);
      }).toPass({ timeout: 10_000 });

      const initialCount = await devicesPage.getLogsLogCount();

      // Scroll to top to trigger backfill
      await devicesPage.scrollLogsToTop();

      // Wait for backfill to complete
      await expect(async () => {
        const count = await devicesPage.getLogsLogCount();
        expect(count).toBeGreaterThan(initialCount);
      }).toPass({ timeout: 10_000 });

      // After backfill, user should NOT be at scrollTop=0 (position was restored)
      const scrollTop = await devicesPage.getLogsScrollTop();
      expect(scrollTop).toBeGreaterThan(0);
    });

    test('does not backfill when all data is already loaded', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('backfill_exhausted_test');
      const device = await devices.create({ deviceEntityId: entityId });

      // Seed only 500 entries — fits in a single page, has_more will be false
      await seedLogs(page, frontendUrl, entityId, 500);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);

      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });
      // Wait for initial load — count should stabilize near 500
      let initialCount = 0;
      await expect(async () => {
        initialCount = await devicesPage.getLogsLogCount();
        expect(initialCount).toBeGreaterThanOrEqual(490);
      }).toPass({ timeout: 10_000 });

      // Scroll to top — should NOT trigger a backfill fetch
      await devicesPage.scrollLogsToTop();

      // Brief wait then verify count is unchanged (no backfill occurred)
      await page.waitForTimeout(1000);
      const countAfter = await devicesPage.getLogsLogCount();
      expect(countAfter).toBe(initialCount);
    });
  });

  test.describe('Download dialog', () => {
    test('download button opens dialog with line-count options', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('download_dialog_test');
      const device = await devices.create({ deviceEntityId: entityId });

      await seedLogs(page, frontendUrl, entityId, 10);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);
      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

      // Click download button
      await devicesPage.logsDownloadButton.click();
      await expect(devicesPage.logsDownloadDialog).toBeVisible();

      // All line-count options should be visible
      for (const count of [100, 500, 1000, 5000, 10000]) {
        await expect(devicesPage.logsDownloadDialogOption(count)).toBeVisible();
      }

      // Submit button should be visible
      await expect(devicesPage.logsDownloadDialogSubmit).toBeVisible();
    });

    test('downloads a log file with requested lines', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('download_file_test');
      const device = await devices.create({ deviceEntityId: entityId });

      await seedLogs(page, frontendUrl, entityId, 200);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);
      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

      // Open dialog and select 100 lines
      await devicesPage.logsDownloadButton.click();
      await expect(devicesPage.logsDownloadDialog).toBeVisible();
      await devicesPage.logsDownloadDialogOption(100).click();

      // Start download and capture the file
      const [download] = await Promise.all([
        page.waitForEvent('download'),
        devicesPage.logsDownloadDialogSubmit.click(),
      ]);

      // Verify filename matches expected pattern
      const filename = download.suggestedFilename();
      expect(filename).toMatch(/^device-.*-logs-.*\.log$/);

      // Read and verify content
      const path = await download.path();
      expect(path).toBeTruthy();
      const fs = await import('fs');
      const content = fs.readFileSync(path!, 'utf-8');
      const lines = content.split('\n').filter((line: string) => line.length > 0);
      expect(lines.length).toBeLessThanOrEqual(100);
      expect(lines.length).toBeGreaterThan(0);
    });

    test('downloads all available lines when fewer than requested', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('download_partial_test');
      const device = await devices.create({ deviceEntityId: entityId });

      // Seed only 50 entries, but request 100
      await seedLogs(page, frontendUrl, entityId, 50);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);
      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

      await devicesPage.logsDownloadButton.click();
      await expect(devicesPage.logsDownloadDialog).toBeVisible();
      await devicesPage.logsDownloadDialogOption(100).click();

      const [download] = await Promise.all([
        page.waitForEvent('download'),
        devicesPage.logsDownloadDialogSubmit.click(),
      ]);

      const path = await download.path();
      expect(path).toBeTruthy();
      const fs = await import('fs');
      const content = fs.readFileSync(path!, 'utf-8');
      const lines = content.split('\n').filter((line: string) => line.length > 0);
      // Should have all 50 entries (fewer than the 100 requested)
      expect(lines.length).toBe(50);
    });

    test('dialog can be closed without downloading', async ({ page, devices, frontendUrl }) => {
      const entityId = devices.randomDeviceEntityId('download_close_test');
      const device = await devices.create({ deviceEntityId: entityId });

      await seedLogs(page, frontendUrl, entityId, 10);

      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoLogs(device.id);
      await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

      // Open dialog
      await devicesPage.logsDownloadButton.click();
      await expect(devicesPage.logsDownloadDialog).toBeVisible();

      // Close it via the Close button
      await devicesPage.logsDownloadDialog.locator('button:has-text("Close")').click();
      await expect(devicesPage.logsDownloadDialog).not.toBeVisible();
    });
  });
});
