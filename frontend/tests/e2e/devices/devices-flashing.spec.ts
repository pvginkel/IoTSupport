import { createHash } from 'node:crypto';
import type { Page } from '@playwright/test';
import type { UiStateTestEvent } from '@/lib/test/test-events';
import { test, expect } from '../../support/fixtures';
import { waitForUiState, waitTestEvent } from '../../support/helpers';
import type { FakeEspOperation } from '../../support/mocks/esptool-mock';
import { installFakeEspDevice, readFakeEspDevice } from '../../support/mocks/fake-esp-device';
import { DevicesPage } from './DevicesPage';

/**
 * Flash Device Tests
 *
 * The USB port and the chip are the only fakes: installFakeEspDevice() hands
 * out a fake Web Serial port, and the esptool-js mock plays its chip. The
 * flash images come from the real backend, seeded through the real firmware
 * upload.
 */

const IMAGES_SCOPE = 'devices.flash-modal.images';
const FLASH_SCOPE = 'devices.flash-modal.flash';

type WriteOperation = Extract<FakeEspOperation, { op: 'write' }>;

function writesOf(operations: FakeEspOperation[]): WriteOperation[] {
  return operations.filter((operation): operation is WriteOperation => operation.op === 'write');
}

/** Every RTS level set on the port, in order */
function rtsLevelsOf(operations: FakeEspOperation[]): boolean[] {
  return operations.flatMap(operation =>
    operation.op === 'signals' && operation.signals.requestToSend !== undefined
      ? [operation.signals.requestToSend]
      : []
  );
}

function md5OfBase64(data: string): string {
  return createHash('md5').update(Buffer.from(data, 'base64')).digest('hex');
}

async function openFlashModal(page: Page, deviceId: number): Promise<{ devicesPage: DevicesPage; loaded: UiStateTestEvent }> {
  const devicesPage = new DevicesPage(page);
  await devicesPage.gotoEdit(deviceId);
  await devicesPage.waitForEditorLoaded();
  await devicesPage.openFlashModal();
  // StrictMode mounts the modal's body twice in the dev build, and the first
  // mount's scope ends as 'aborted' before the images arrive
  const loaded = await waitTestEvent<UiStateTestEvent>(
    page,
    'ui_state',
    event => event.scope === IMAGES_SCOPE && event.phase === 'ready' && event.metadata?.status !== 'aborted'
  );
  return { devicesPage, loaded };
}

test.describe('Flash Device', () => {
  test('sits beside Provision Device in edit mode', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    await expect(devicesPage.flashDeviceButton).toBeVisible();
    await expect(devicesPage.flashDeviceButton).toHaveText(/Flash Device/);
    await expect(devicesPage.usbActions.locator('[data-testid="devices.editor.flash-device"]')).toBeVisible();
    await expect(devicesPage.usbActions.locator('[data-testid="devices.editor.provision-device"]')).toBeVisible();
  });

  test('is absent when creating a new device', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['editor'] });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    await expect(devicesPage.flashDeviceButton).not.toBeVisible();
  });

  test('writes every image the backend serves at its offset, verifies each and resets the device', async ({ page, devices, deviceModels }) => {
    const model = await deviceModels.create();
    await deviceModels.seedFirmware(model.id, { version: '2.3.4' });
    const device = await devices.create({ deviceModelId: model.id });
    await installFakeEspDevice(page);

    const { devicesPage, loaded } = await openFlashModal(page, device.id);

    // It names the version it is about to write, and every image
    expect(loaded.metadata).toMatchObject({ flashStatus: 'flashable', firmwareVersion: '2.3.4', imageCount: 4 });
    await expect(devicesPage.flashModalFirmwareVersion).toHaveText('2.3.4');
    await expect(devicesPage.flashModalImages).toHaveCount(4);

    await devicesPage.flashModalConnectButton.click();
    const flashed = await waitForUiState(page, FLASH_SCOPE, 'ready');
    expect(flashed.metadata).toMatchObject({ outcome: 'success', firmwareVersion: '2.3.4' });
    await expect(devicesPage.flashModalSuccessMessage).toBeVisible();

    const served = await devices.getFlashImages(device.id);
    expect(served.status).toBe('flashable');
    const images = served.flash!.images;
    // The seeded build puts its app at 0x20000, not at the usual 0x10000
    expect(images.map(image => image.offset)).toEqual([0x0, 0x8000, 0xd000, 0x20000]);

    const { portRequests, operations } = await readFakeEspDevice(page);
    expect(portRequests).toBe(1);

    // Every image the backend serves, byte for byte, each at its own offset
    const writes = writesOf(operations);
    expect(writes.map(write => ({ address: write.address, data: write.data }))).toEqual(
      images.map(image => ({ address: image.offset, data: image.data }))
    );

    // Each verified against its true MD5, and nothing erased
    writes.forEach((write, index) => {
      expect(write.md5).toBe(md5OfBase64(images[index].data));
      expect(write.eraseAll).toBe(false);
    });

    // Reset after the last write: RTS pulls EN low, then releases it
    const lastWrite = operations.map(operation => operation.op).lastIndexOf('write');
    expect(rtsLevelsOf(operations.slice(0, lastWrite))).toEqual([]);
    expect(rtsLevelsOf(operations.slice(lastWrite + 1))).toEqual([true, false]);
  });

  test('says the model has no firmware and writes nothing', async ({ page, devices, deviceModels }) => {
    const model = await deviceModels.create();
    const device = await devices.create({ deviceModelId: model.id });
    await installFakeEspDevice(page);

    const { devicesPage, loaded } = await openFlashModal(page, device.id);

    expect(loaded.metadata).toMatchObject({ flashStatus: 'no_firmware', imageCount: 0 });
    await expect(devicesPage.flashModalNotFlashable).toHaveAttribute('data-status', 'no_firmware');
    await expect(devicesPage.flashModalNotFlashable).toContainText("This device's model has no firmware");
    await expect(devicesPage.flashModalConnectButton).toHaveCount(0);

    expect(await readFakeEspDevice(page)).toEqual(expect.objectContaining({ portRequests: 0, operations: [] }));
  });

  test('says the current version has no flash images and writes nothing', async ({ page, devices, deviceModels }) => {
    const model = await deviceModels.create();
    await deviceModels.seedFirmware(model.id, { version: '1.4.0', flashImages: false });
    const device = await devices.create({ deviceModelId: model.id });
    await installFakeEspDevice(page);

    const { devicesPage, loaded } = await openFlashModal(page, device.id);

    expect(loaded.metadata).toMatchObject({ flashStatus: 'no_flash_images', firmwareVersion: '1.4.0', imageCount: 0 });
    await expect(devicesPage.flashModalNotFlashable).toHaveAttribute('data-status', 'no_flash_images');
    await expect(devicesPage.flashModalNotFlashable).toContainText('Firmware 1.4.0 was stored without flash images');
    await expect(devicesPage.flashModalConnectButton).toHaveCount(0);

    expect(await readFakeEspDevice(page)).toEqual(expect.objectContaining({ portRequests: 0, operations: [] }));
  });

  test('refuses a chip other than the one the build targets before writing', async ({ page, devices, deviceModels }) => {
    const model = await deviceModels.create();
    await deviceModels.seedFirmware(model.id, { version: '3.0.0', chip: 'esp32c3' });
    const device = await devices.create({ deviceModelId: model.id });
    // The fake device's chip is an ESP32-S3
    await installFakeEspDevice(page);

    const { devicesPage } = await openFlashModal(page, device.id);
    await devicesPage.flashModalConnectButton.click();

    const flashed = await waitForUiState(page, FLASH_SCOPE, 'ready');
    expect(flashed.metadata).toMatchObject({ outcome: 'error', failedPhase: 'connecting', firmwareVersion: '3.0.0' });
    await expect(devicesPage.flashModalErrorMessage).toHaveText(
      'The connected chip is an ESP32-S3, but firmware 3.0.0 is built for esp32c3. Nothing was written.'
    );

    // Connected, but nothing written and no reset
    const { portRequests, operations } = await readFakeEspDevice(page);
    expect(portRequests).toBe(1);
    expect(writesOf(operations)).toEqual([]);
    expect(rtsLevelsOf(operations)).toEqual([]);
  });

  test('fails the flash when an image read back from the device does not match', async ({ page, devices, deviceModels }) => {
    const model = await deviceModels.create();
    await deviceModels.seedFirmware(model.id);
    const device = await devices.create({ deviceModelId: model.id });
    // The chip's flash holds other bytes than were sent to it
    await installFakeEspDevice(page, { verificationResult: 'mismatch' });

    const { devicesPage } = await openFlashModal(page, device.id);
    await devicesPage.flashModalConnectButton.click();

    const flashed = await waitForUiState(page, FLASH_SCOPE, 'ready');
    expect(flashed.metadata).toMatchObject({ outcome: 'error', failedPhase: 'writing' });
    await expect(devicesPage.flashModalErrorMessage).toHaveText(
      'bootloader/bootloader.bin at 0x0: MD5 of file does not match data in flash!'
    );
    await expect(devicesPage.flashModalSuccessMessage).toHaveCount(0);
    await expect(devicesPage.flashModalRetryButton).toBeVisible();

    // The flash stopped at the first image and did not reset the device
    const { operations } = await readFakeEspDevice(page);
    expect(writesOf(operations).map(write => write.address)).toEqual([0x0]);
    expect(rtsLevelsOf(operations)).toEqual([]);
  });
});
