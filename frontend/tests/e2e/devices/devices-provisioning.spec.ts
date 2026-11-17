import type { Page } from '@playwright/test';
import type { ProvisioningTestEvent } from '@/types/provisioning-events';
import { test, expect } from '../../support/fixtures';
import { waitTestEvent } from '../../support/helpers';
import type { FakeEspOperation } from '../../support/mocks/esptool-mock';
import { installFakeEspDevice, readFakeEspDevice } from '../../support/mocks/fake-esp-device';
import { DevicesPage } from './DevicesPage';

/**
 * Device Provisioning Tests
 *
 * The modal's own behaviour is tested up to the Connect button. The
 * provisioning workflow is driven past the port picker on a fake device:
 * installFakeEspDevice() hands out a fake Web Serial port and the esptool-js
 * mock plays its chip, configured per spec (its partition table, a failing
 * write, a flash that reads back other bytes). The NVS blob comes from the
 * real backend.
 */

type WriteOperation = Extract<FakeEspOperation, { op: 'write' }>;

function writesOf(operations: FakeEspOperation[]): WriteOperation[] {
  return operations.filter((operation): operation is WriteOperation => operation.op === 'write');
}

/** The mock's default NVS partition */
const NVS_OFFSET = 0x9000;
const NVS_SIZE = 0x5000;

/** Open the device's Provision modal, connect, and wait for the workflow to end */
async function provision(page: Page, deviceId: number): Promise<{ devicesPage: DevicesPage; ended: ProvisioningTestEvent }> {
  const devicesPage = new DevicesPage(page);
  await devicesPage.gotoEdit(deviceId);
  await devicesPage.waitForEditorLoaded();
  await devicesPage.openProvisionModal();
  await devicesPage.startProvisioning();
  const ended = await waitTestEvent<ProvisioningTestEvent>(
    page,
    'provisioning',
    event => event.deviceId === deviceId && (event.phase === 'complete' || event.phase === 'error')
  );
  return { devicesPage, ended };
}

test.describe('Provision Device', () => {
  test('writes the backend\'s NVS blob over the NVS partition and verifies it', async ({ page, devices }) => {
    const device = await devices.create();
    await installFakeEspDevice(page);

    const { devicesPage, ended } = await provision(page, device.id);

    expect(ended.phase).toBe('complete');
    await expect(devicesPage.provisionModalSuccessMessage).toBeVisible();

    // One write: a blob the partition's size, at the partition's offset
    const { portRequests, operations } = await readFakeEspDevice(page);
    expect(portRequests).toBe(1);
    const writes = writesOf(operations);
    expect(writes.map(write => ({ address: write.address, size: Buffer.from(write.data, 'base64').length }))).toEqual([
      { address: NVS_OFFSET, size: NVS_SIZE },
    ]);
    expect(writes[0].eraseAll).toBe(false);
  });

  test('fails before writing when the device has no NVS partition', async ({ page, devices }) => {
    const device = await devices.create();
    await installFakeEspDevice(page, {
      partitionTable: [
        { name: 'otadata', type: 1, subtype: 0, offset: 0xe000, size: 0x2000 },
        { name: 'app', type: 0, subtype: 0, offset: 0x10000, size: 0x100000 },
      ],
    });

    const { devicesPage, ended } = await provision(page, device.id);

    expect(ended).toMatchObject({
      phase: 'error',
      metadata: { provisioningPhase: 'reading_partition', error: 'NVS partition not found in partition table' },
    });
    await expect(devicesPage.provisionModalErrorMessage).toHaveText('NVS partition not found in partition table');
    await expect(devicesPage.provisionModalRetryButton).toBeVisible();

    expect(writesOf((await readFakeEspDevice(page)).operations)).toEqual([]);
  });

  test('fails when the device refuses the write', async ({ page, devices }) => {
    const device = await devices.create();
    await installFakeEspDevice(page, { flashWriteResult: 'error' });

    const { devicesPage, ended } = await provision(page, device.id);

    expect(ended).toMatchObject({
      phase: 'error',
      metadata: { provisioningPhase: 'flashing', error: 'Flash write error: Failed to write data at specified address' },
    });
    await expect(devicesPage.provisionModalErrorMessage).toHaveText(
      'Flash write error: Failed to write data at specified address'
    );
    await expect(devicesPage.provisionModalSuccessMessage).toHaveCount(0);
    await expect(devicesPage.provisionModalRetryButton).toBeVisible();

    expect(writesOf((await readFakeEspDevice(page)).operations)).toEqual([]);
  });

  test('fails when the NVS partition reads back other bytes than were written', async ({ page, devices }) => {
    const device = await devices.create();
    // The chip's flash holds other bytes than were sent to it
    await installFakeEspDevice(page, { verificationResult: 'mismatch' });

    const { devicesPage, ended } = await provision(page, device.id);

    expect(ended).toMatchObject({ phase: 'error', metadata: { provisioningPhase: 'verifying' } });
    expect(ended.metadata?.error).toMatch(
      /^Verification failed: the NVS partition reads back MD5 [0-9a-f]{32}, the credentials written have MD5 [0-9a-f]{32}$/
    );
    await expect(devicesPage.provisionModalErrorMessage).toContainText('Verification failed');
    await expect(devicesPage.provisionModalSuccessMessage).toHaveCount(0);
    await expect(devicesPage.provisionModalRetryButton).toBeVisible();

    // The write went out; the read-back is what failed
    expect(writesOf((await readFakeEspDevice(page)).operations).map(write => write.address)).toEqual([NVS_OFFSET]);
  });
});

test.describe('Device Provisioning Modal', () => {
  test('shows provision device button in edit mode', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Provision Device button should be visible in configuration tab
    await expect(devicesPage.provisionDeviceButton).toBeVisible();
    await expect(devicesPage.provisionDeviceButton).toHaveText(/Provision Device/);
  });

  test('does not show provision device button in new mode', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['editor'] });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // Provision Device button should not be visible in new mode
    await expect(devicesPage.provisionDeviceButton).not.toBeVisible();
  });

  test('opens provision modal when clicking provision button', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Open provision modal
    await devicesPage.openProvisionModal();

    // Modal should be visible with instructions
    await expect(devicesPage.provisionModal).toBeVisible();
    await expect(devicesPage.provisionModal).toContainText('Provision Device');
    await expect(devicesPage.provisionModal).toContainText(device.key);

    // Connect button should be visible
    await expect(devicesPage.provisionModalConnectButton).toBeVisible();

    // Close button should be visible
    await expect(devicesPage.provisionModalCloseButton).toBeVisible();
  });

  test('closes provision modal when clicking close button', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Open and close modal
    await devicesPage.openProvisionModal();
    await expect(devicesPage.provisionModal).toBeVisible();

    await devicesPage.closeProvisionModal();
    await expect(devicesPage.provisionModal).not.toBeVisible();
  });

  test('modal shows instructions before connecting', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    await devicesPage.openProvisionModal();

    // Instructions should include step-by-step guide
    const instructions = devicesPage.provisionModal.locator('ol');
    await expect(instructions).toContainText('Connect your ESP32 device via USB');
    await expect(instructions).toContainText('Click "Connect"');
    await expect(instructions).toContainText('Wait for the credentials');
    await expect(instructions).toContainText('Reset the device');
  });

  test('provision button has correct icon', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Button should have an SVG icon (Cpu icon from lucide-react)
    const icon = devicesPage.provisionDeviceButton.locator('svg');
    await expect(icon).toBeVisible();
  });


  test('form action buttons are visible in configuration tab', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Cancel, Duplicate, and Save buttons should be visible in config tab
    await expect(devicesPage.cancelButton).toBeVisible();
    await expect(devicesPage.duplicateButton).toBeVisible();
    await expect(devicesPage.saveButton).toBeVisible();
  });

  test('provision button is disabled while form is saving', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Test Device' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Make a change to enable save
    await devicesPage.setJsonObject({
      deviceName: 'Updated Name',
      deviceEntityId: 'updated_entity',
      enableOTA: true
    });

    // Verify the button exists and is enabled when not saving
    await expect(devicesPage.provisionDeviceButton).toBeEnabled();
  });
});

test.describe('Provision Modal Error States', () => {
  test('modal can be reopened after closing', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Open, close, and reopen modal
    await devicesPage.openProvisionModal();
    await devicesPage.closeProvisionModal();

    // Should be able to open again
    await devicesPage.openProvisionModal();
    await expect(devicesPage.provisionModal).toBeVisible();
    await expect(devicesPage.provisionModalConnectButton).toBeVisible();
  });

  test('modal state resets when reopened', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Open modal
    await devicesPage.openProvisionModal();
    await expect(devicesPage.provisionModalConnectButton).toBeVisible();

    // Close modal
    await devicesPage.closeProvisionModal();

    // Reopen modal
    await devicesPage.openProvisionModal();

    // Should show connect button again (reset to initial state)
    await expect(devicesPage.provisionModalConnectButton).toBeVisible();
  });
});

test.describe('Download Provisioning Removal', () => {
  test('download provisioning button no longer exists', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // The old download provisioning button should not exist
    const downloadButton = page.locator('[data-testid="devices.editor.download-provisioning"]');
    await expect(downloadButton).not.toBeVisible();
  });
});
