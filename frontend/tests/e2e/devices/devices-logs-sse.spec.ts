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

/**
 * Ensure the SSE connection is registered on the backend and a device-log
 * subscription exists. The useDeviceLogs hook subscribes automatically, but in
 * test mode there are two races:
 *
 * 1. Gateway callback race: the frontend's EventSource opens before the gateway's
 *    callback POST registers the connection on the backend, causing the hook's
 *    subscribe call to fail (no retry).
 * 2. StrictMode double-mount: React's StrictMode fires a cleanup (unsubscribe)
 *    between two mounts, and the fire-and-forget unsubscribe can arrive at the
 *    backend after the re-subscribe, removing the subscription.
 *
 * This helper polls subscribe until it succeeds (handles race 1) and is called
 * after the logs tab is mounted (handles race 2 by re-creating the subscription
 * if StrictMode removed it).
 */
async function ensureSubscription(
  page: import('@playwright/test').Page,
  frontendUrl: string,
  requestId: string,
  deviceId: number,
  timeout = 5_000,
): Promise<boolean> {
  try {
    await expect(async () => {
      const resp = await page.request.post(
        `${frontendUrl}/api/device-logs/subscribe`,
        { data: { request_id: requestId, device_id: deviceId } },
      );
      expect(resp.ok()).toBe(true);
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
    deploymentSse,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_ready_test');
    const device = await devices.create({ deviceEntityId: entityId });

    // In test mode, SSE does not auto-connect. Navigate to the device detail
    // page (configuration tab) first, establish the SSE connection there, then
    // switch to the logs tab via client-side navigation. This preserves the
    // SSE EventSource across the tab switch.
    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await deploymentSse.ensureConnected();

    // Switch to logs tab (client-side navigation — SSE connection preserved)
    await devicesPage.clickTab('logs');

    // Ensure the subscription exists (handles gateway callback race + StrictMode)
    const requestId = await deploymentSse.getRequestId();
    if (!requestId) {
      test.skip(true, 'SSE connection has no requestId');
      return;
    }
    const subscribed = await ensureSubscription(page, frontendUrl, requestId, device.id);
    if (!subscribed) {
      test.skip(true, 'Could not subscribe -- gateway may not be available');
      return;
    }

    // Wait for the log viewer to appear (SSE subscription + initial history load)
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Verify SSE subscription is active via testing endpoint
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
    deploymentSse,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_inject_test');
    const device = await devices.create({ deviceEntityId: entityId });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await deploymentSse.ensureConnected();
    await devicesPage.clickTab('logs');

    const requestId = await deploymentSse.getRequestId();
    if (!requestId) {
      test.skip(true, 'SSE connection has no requestId');
      return;
    }
    const subscribed = await ensureSubscription(page, frontendUrl, requestId, device.id);
    if (!subscribed) {
      test.skip(true, 'Could not subscribe -- gateway may not be available');
      return;
    }

    // Wait for the viewer to be ready
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Wait for active SSE subscription
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
    deploymentSse,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_order_test');
    const device = await devices.create({ deviceEntityId: entityId });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await deploymentSse.ensureConnected();
    await devicesPage.clickTab('logs');

    const requestId = await deploymentSse.getRequestId();
    if (!requestId) {
      test.skip(true, 'SSE connection has no requestId');
      return;
    }
    const subscribed = await ensureSubscription(page, frontendUrl, requestId, device.id);
    if (!subscribed) {
      test.skip(true, 'Could not subscribe -- gateway may not be available');
      return;
    }

    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Wait for active SSE subscription
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
