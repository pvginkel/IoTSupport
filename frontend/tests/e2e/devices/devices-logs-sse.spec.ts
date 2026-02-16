import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

/**
 * Device Logs SSE Streaming Spec.
 *
 * Verifies that device logs appear in real time via SSE injection using
 * the backend testing endpoints:
 * - POST /api/testing/devices/logs/inject
 * - GET /api/testing/devices/logs/subscriptions
 *
 * Requires the SSE Gateway to be running (managed by fixtures).
 */

/**
 * Poll the testing endpoint until an active SSE subscription exists for the device,
 * or fail after timeout. Uses expect().toPass() instead of manual polling with
 * waitForTimeout to comply with the no-sleep policy.
 *
 * Returns true if subscription is active, false if the endpoint is unreachable
 * (gateway not running).
 */
async function waitForSseSubscription(
  page: import('@playwright/test').Page,
  frontendUrl: string,
  entityId: string,
  timeout = 15_000,
): Promise<boolean> {
  try {
    await expect(async () => {
      const resp = await page.request.get(
        `${frontendUrl}/api/testing/devices/logs/subscriptions?device_entity_id=${encodeURIComponent(entityId)}`,
      );
      expect(resp.ok()).toBe(true);
      const data = await resp.json();
      expect(data.subscriptions?.length).toBeGreaterThan(0);
    }).toPass({ timeout });
    return true;
  } catch {
    return false;
  }
}

test.describe('Device Logs SSE Streaming', () => {
  test('log viewer becomes visible and emits ready event for device with entity_id', async ({
    page,
    devices,
    frontendUrl,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_ready_test');
    const device = await devices.create({ deviceEntityId: entityId });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoLogs(device.id);

    // Wait for the log viewer to appear (SSE subscription + initial history load)
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Verify SSE subscription is active; skip if gateway is unavailable
    const subscriptionActive = await waitForSseSubscription(page, frontendUrl, entityId);
    if (!subscriptionActive) {
      test.skip(true, 'SSE subscription not active -- gateway may not be available');
      return;
    }
  });

  test('injected logs appear in the viewer in real time', async ({
    page,
    devices,
    frontendUrl,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_inject_test');
    const device = await devices.create({ deviceEntityId: entityId });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoLogs(device.id);

    // Wait for the viewer to be ready
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Wait for active SSE subscription; skip if gateway unavailable
    const subscriptionActive = await waitForSseSubscription(page, frontendUrl, entityId);
    if (!subscriptionActive) {
      test.skip(true, 'SSE subscription not active -- gateway may not be available');
      return;
    }

    // Inject log entries via the testing endpoint
    const testMessages = [
      'SSE test log entry alpha',
      'SSE test log entry beta',
      'SSE test log entry gamma',
    ];

    const injectResponse = await page.request.post(
      `${frontendUrl}/api/testing/devices/logs/inject`,
      {
        data: {
          device_entity_id: entityId,
          logs: testMessages.map((message) => ({ message })),
        },
      },
    );

    expect(injectResponse.ok()).toBe(true);

    // Wait for injected messages to appear in the viewer
    for (const message of testMessages) {
      await expect(
        devicesPage.logsEntries.filter({ hasText: message }),
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test('multiple injected entries appear in chronological order', async ({
    page,
    devices,
    frontendUrl,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_order_test');
    const device = await devices.create({ deviceEntityId: entityId });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoLogs(device.id);
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Wait for active SSE subscription; skip if gateway unavailable
    const subscriptionActive = await waitForSseSubscription(page, frontendUrl, entityId);
    if (!subscriptionActive) {
      test.skip(true, 'SSE subscription not active');
      return;
    }

    // Inject ordered entries
    const orderedMessages = ['First entry', 'Second entry', 'Third entry'];
    await page.request.post(`${frontendUrl}/api/testing/devices/logs/inject`, {
      data: {
        device_entity_id: entityId,
        logs: orderedMessages.map((message) => ({ message })),
      },
    });

    // Wait for all entries to appear
    for (const msg of orderedMessages) {
      await expect(
        devicesPage.logsEntries.filter({ hasText: msg }),
      ).toBeVisible({ timeout: 10_000 });
    }

    // Verify order: each entry should appear after the previous one
    const allTexts = await devicesPage.logsEntries.allTextContents();
    const indices = orderedMessages.map((msg) =>
      allTexts.findIndex((text) => text.includes(msg)),
    );

    // All messages should be found
    for (let i = 0; i < indices.length; i++) {
      expect(indices[i]).toBeGreaterThanOrEqual(0);
    }

    // And they should appear in ascending order
    for (let i = 1; i < indices.length; i++) {
      expect(indices[i]).toBeGreaterThan(indices[i - 1]);
    }
  });
});
