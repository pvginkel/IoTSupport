import { test, expect } from '../../support/fixtures';
import type { DeploymentSseHelper } from '../../support/helpers/deployment-sse';
import { DevicesPage } from './DevicesPage';

/**
 * Device Logs SSE Streaming Spec.
 *
 * Verifies that device logs appear in real time via SSE injection using
 * the backend testing endpoints:
 * - POST /api/testing/devices/logs/inject
 * - GET /api/testing/devices/logs/subscriptions
 * - POST /api/testing/devices/logs/drop-stream
 *
 * The SSE stream is the backend's own (GET /api/sse/stream), served by every
 * worker's backend.
 */

/**
 * Poll the testing endpoint until an active SSE subscription exists for the
 * device. Uses expect().toPass() instead of manual polling with
 * waitForTimeout to comply with the no-sleep policy.
 */
async function expectSseSubscription(
  page: import('@playwright/test').Page,
  frontendUrl: string,
  entityId: string,
  timeout = 15_000,
): Promise<void> {
  await expect(async () => {
    const resp = await page.request.get(
      `${frontendUrl}/api/testing/devices/logs/subscriptions?device_entity_id=${encodeURIComponent(entityId)}`,
    );
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data.subscriptions?.length).toBeGreaterThan(0);
  }).toPass({ timeout });
}

/**
 * Ensure a device-log subscription exists for the page's SSE connection. The
 * useDeviceLogs hook subscribes automatically, but React's StrictMode fires a
 * cleanup (unsubscribe) between its two mounts, and the fire-and-forget
 * unsubscribe can arrive at the backend after the re-subscribe, removing the
 * subscription. Called after the logs tab is mounted, this re-creates it.
 * The backend registers the connection before it sends `ready`, so once
 * ensureConnected() returns the subscribe is accepted.
 */
async function ensureSubscription(
  page: import('@playwright/test').Page,
  frontendUrl: string,
  deploymentSse: DeploymentSseHelper,
  deviceId: number,
): Promise<void> {
  const requestId = await deploymentSse.getRequestId();
  expect(requestId).toBeTruthy();
  const resp = await page.request.post(
    `${frontendUrl}/api/device-logs/subscribe`,
    { data: { request_id: requestId, device_id: deviceId } },
  );
  expect(resp.ok()).toBe(true);
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

    // Ensure the subscription exists (StrictMode may have removed it)
    await ensureSubscription(page, frontendUrl, deploymentSse, device.id);

    // Wait for the log viewer to appear (SSE subscription + initial history load)
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Verify SSE subscription is active via testing endpoint
    await expectSseSubscription(page, frontendUrl, entityId);
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

    await ensureSubscription(page, frontendUrl, deploymentSse, device.id);

    // Wait for the viewer to be ready
    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Wait for active SSE subscription
    await expectSseSubscription(page, frontendUrl, entityId);

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

  test('logs keep streaming after the stream is dropped server-side', async ({
    page,
    devices,
    frontendUrl,
    deploymentSse,
  }) => {
    const entityId = devices.randomDeviceEntityId('sse_drop_test');
    const device = await devices.create({ deviceEntityId: entityId });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await deploymentSse.ensureConnected();
    await devicesPage.clickTab('logs');

    await ensureSubscription(page, frontendUrl, deploymentSse, device.id);

    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });
    await expectSseSubscription(page, frontendUrl, entityId);

    // End the stream server-side, as a pod restart does: the backend drops
    // the subscription, and the browser reconnects with the same request_id
    const requestId = await deploymentSse.getRequestId();
    expect(requestId).toBeTruthy();
    const dropResponse = await page.request.post(
      `${frontendUrl}/api/testing/devices/logs/drop-stream`,
      { data: { request_id: requestId } },
    );
    expect(dropResponse.ok()).toBe(true);

    // The hook subscribes anew once the stream is connected again
    await expectSseSubscription(page, frontendUrl, entityId);
    expect(await deploymentSse.getRequestId()).toBe(requestId);

    const message = 'SSE test log entry after reconnect';
    const injectResponse = await page.request.post(
      `${frontendUrl}/api/testing/devices/logs/inject`,
      {
        data: {
          device_entity_id: entityId,
          logs: [{ message }],
        },
      },
    );
    expect(injectResponse.ok()).toBe(true);

    await expect(
      devicesPage.logsEntries.filter({ hasText: message }),
    ).toBeVisible({ timeout: 10_000 });
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

    await ensureSubscription(page, frontendUrl, deploymentSse, device.id);

    await expect(devicesPage.logsViewer).toBeVisible({ timeout: 15_000 });

    // Wait for active SSE subscription
    await expectSseSubscription(page, frontendUrl, entityId);

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
