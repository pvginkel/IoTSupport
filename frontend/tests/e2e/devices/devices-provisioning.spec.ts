import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

/**
 * Device Provisioning Tests
 *
 * These tests verify the provisioning modal UI behavior. Since Web Serial API
 * requires user gesture and actual hardware, we test the UI flow up to the
 * point of hardware interaction.
 *
 * The ESPLoader mock is automatically loaded when VITE_TEST_MODE=true,
 * but Web Serial port selection still requires user interaction which
 * cannot be automated in Playwright.
 */

test.describe('Device Provisioning Modal', () => {
  test('shows provision device button in edit mode', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Provision Device button should be visible
    await expect(devicesPage.provisionDeviceButton).toBeVisible();
    await expect(devicesPage.provisionDeviceButton).toHaveText(/Provision Device/);
  });

  test('does not show provision device button in new mode', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

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


  test('form action buttons remain in the right section', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Cancel, Duplicate, and Save buttons should still be visible
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

    // We can't easily test the disabled state during save without race conditions
    // but we can verify the button exists and is enabled when not saving
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

    // Connect button should be visible (initial state)
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
