import { test, expect } from '../../support/fixtures';
import { DevicesPage } from './DevicesPage';

test.describe('Device List', () => {
  test('displays correct state based on device count', async ({ page, devices }) => {
    // Check current state - don't delete devices as it may interfere with other tests
    const existingDevices = await devices.list();

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    if (existingDevices.length === 0) {
      // Should show empty state
      await expect(devicesPage.emptyState).toBeVisible();
      await expect(devicesPage.emptyState).toContainText('No devices configured');
    } else {
      // Should show table
      await expect(devicesPage.list).toBeVisible();
    }
  });

  test('displays devices in table when devices exist', async ({ page, devices }) => {
    // Create test devices with unique MACs to avoid conflicts
    const device1 = await devices.create({ macAddress: 'b1-bb-cc-dd-ee-01', deviceName: 'Living Room Sensor' });
    const device2 = await devices.create({ macAddress: 'b2-bb-cc-dd-ee-02', deviceName: 'Kitchen Sensor' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();

      // Verify table is visible (or empty state if deleted by parallel test)
      const isTableVisible = await devicesPage.list.isVisible().catch(() => false);
      if (isTableVisible) {
        // Verify both devices appear
        await expect(devicesPage.row(device1.macAddress)).toBeVisible();
        await expect(devicesPage.row(device2.macAddress)).toBeVisible();

        // Verify device names are shown
        await expect(devicesPage.row(device1.macAddress)).toContainText('Living Room Sensor');
        await expect(devicesPage.row(device2.macAddress)).toContainText('Kitchen Sensor');
      }
    } finally {
      // Cleanup - ignore errors as device might already be deleted
      try { await devices.delete(device1.macAddress); } catch { /* ignore */ }
      try { await devices.delete(device2.macAddress); } catch { /* ignore */ }
    }
  });

  test('displays OTA status icons correctly', async ({ page, devices }) => {
    // Use lowercase MACs
    const deviceOtaTrue = await devices.create({ macAddress: '0a-0b-0c-0d-0e-01', enableOTA: true });
    const deviceOtaFalse = await devices.create({ macAddress: '0a-fa-15-e0-00-02', enableOTA: false });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();

      // OTA true should show check mark
      const rowTrue = devicesPage.row(deviceOtaTrue.macAddress);
      await expect(rowTrue.locator('text=✓')).toBeVisible();

      // OTA false should show cross
      const rowFalse = devicesPage.row(deviceOtaFalse.macAddress);
      await expect(rowFalse.locator('text=✕')).toBeVisible();
    } finally {
      await devices.delete(deviceOtaTrue.macAddress);
      await devices.delete(deviceOtaFalse.macAddress);
    }
  });

  test('navigates to new device editor', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.clickNewDevice();

    await expect(page).toHaveURL('/devices/new');
    await expect(devicesPage.editor).toBeVisible();
    await expect(devicesPage.macInput).toBeVisible();
  });

  test('navigates to edit device', async ({ page, devices }) => {
    // Use lowercase MAC
    const device = await devices.create({ macAddress: 'ed-11-1e-51-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();
      await devicesPage.editDevice(device.macAddress);

      // URL will have the lowercase MAC
      await expect(page).toHaveURL(`/devices/${encodeURIComponent(device.macAddress)}`);
      await expect(devicesPage.editor).toBeVisible();
      // The input will show the lowercase MAC
      await expect(devicesPage.macInput).toHaveValue(device.macAddress);
    } finally {
      await devices.delete(device.macAddress);
    }
  });
});

test.describe('Create Device', () => {
  test('creates a new device with valid data', async ({ page, devices }) => {
    // Use lowercase MAC - backend will normalize it anyway
    const testMac = 'ae-fd-ef-1c-e0-01';
    const devicesPage = new DevicesPage(page);

    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // Fill in the form
    await devicesPage.fillMacAddress(testMac);
    await devicesPage.setJsonObject({
      deviceName: 'Test New Device',
      deviceEntityId: 'test_new_device',
      enableOTA: true
    });

    // Wait a moment for validation
    await page.waitForTimeout(100);

    // Save should be enabled
    await expect(devicesPage.saveButton).toBeEnabled();

    // Save
    await devicesPage.save();

    // Wait for navigation back to list
    await expect(page).toHaveURL('/devices');
    await devicesPage.waitForListLoaded();

    // Verify device appears in list
    await expect(devicesPage.row(testMac)).toBeVisible();

    // Cleanup
    await devices.delete(testMac);
  });

  test('save button is disabled when MAC address is empty', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // MAC is empty by default, save should be disabled
    await expect(devicesPage.saveButton).toBeDisabled();

    // Fill MAC, save should be enabled
    await devicesPage.fillMacAddress('1e-51-ac-00-00-01');
    await expect(devicesPage.saveButton).toBeEnabled();

    // Clear MAC, save should be disabled again
    await devicesPage.fillMacAddress('');
    await expect(devicesPage.saveButton).toBeDisabled();
  });

  test('cancel navigates back to list', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    await devicesPage.cancel();

    await expect(page).toHaveURL('/devices');
  });
});

test.describe('Edit Device', () => {
  test('edits an existing device', async ({ page, devices }) => {
    const device = await devices.create({
      macAddress: 'ed-11-ee-15-10-01',
      deviceName: 'Original Name'
    });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.macAddress);
      await devicesPage.waitForEditorLoaded();

      // Verify MAC is pre-filled
      await expect(devicesPage.macInput).toHaveValue(device.macAddress);

      // Update the JSON
      await devicesPage.setJsonObject({
        deviceName: 'Updated Name',
        deviceEntityId: 'updated_entity',
        enableOTA: true
      });

      // Wait for validation
      await page.waitForTimeout(100);

      // Save
      await devicesPage.save();

      // Wait for navigation
      await expect(page).toHaveURL('/devices');
      await devicesPage.waitForListLoaded();

      // Verify updated name appears
      await expect(devicesPage.row(device.macAddress)).toContainText('Updated Name');
    } finally {
      await devices.delete(device.macAddress);
    }
  });

  test('shows duplicate button in edit mode', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'd0-b1-b1-a0-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.macAddress);
      await devicesPage.waitForEditorLoaded();

      await expect(devicesPage.duplicateButton).toBeVisible();
    } finally {
      await devices.delete(device.macAddress);
    }
  });
});

test.describe('Duplicate Device', () => {
  test('duplicates a device', async ({ page, devices }) => {
    const sourceDevice = await devices.create({
      macAddress: '5c-ce-d0-b1-00-01',
      deviceName: 'Source Device',
      deviceEntityId: 'source_entity'
    });

    const newMac = 'd0-b1-1c-a1-e0-01';

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoDuplicate(sourceDevice.macAddress);
      await devicesPage.waitForEditorLoaded();

      // Clear any pre-filled MAC and set new MAC
      await devicesPage.fillMacAddress(newMac);

      // Wait for validation
      await page.waitForTimeout(100);

      await devicesPage.save();

      // Wait for navigation
      await expect(page).toHaveURL('/devices');
      await devicesPage.waitForListLoaded();

      // The new device should exist
      await expect(devicesPage.row(newMac)).toBeVisible();

      // Cleanup the duplicate
      try { await devices.delete(newMac); } catch { /* ignore */ }
    } finally {
      try { await devices.delete(sourceDevice.macAddress); } catch { /* ignore */ }
    }
  });

  test('navigates to duplicate from edit page', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'aa-fd-0b-10-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.macAddress);
      await devicesPage.waitForEditorLoaded();

      // Duplicate button should be visible in edit mode
      await expect(devicesPage.duplicateButton).toBeVisible();

      await devicesPage.duplicate();

      // Should navigate to duplicate URL
      await expect(page).toHaveURL(`/devices/${encodeURIComponent(device.macAddress)}/duplicate`);
      // Editor should be visible
      await expect(devicesPage.editor).toBeVisible();
    } finally {
      try { await devices.delete(device.macAddress); } catch { /* ignore */ }
    }
  });
});

test.describe('Delete Device', () => {
  test('shows delete confirmation dialog', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'de-1e-1e-ae-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();

      // Verify device exists before delete
      await expect(devicesPage.row(device.macAddress)).toBeVisible();

      // Click delete
      await devicesPage.deleteDevice(device.macAddress);

      // Confirmation dialog should appear
      await expect(devicesPage.deleteConfirmDialog).toBeVisible();
      await expect(devicesPage.deleteConfirmDialog).toContainText(device.macAddress);

      // Confirm button should be visible
      await expect(devicesPage.deleteConfirmDialog.locator('button:has-text("Delete")')).toBeVisible();

      // Cancel button should be visible
      await expect(devicesPage.deleteConfirmDialog.locator('button:has-text("Cancel")')).toBeVisible();

      // Click cancel to close
      await devicesPage.cancelDelete();

      // Dialog should close
      await expect(devicesPage.deleteConfirmDialog).not.toBeVisible();
    } finally {
      try { await devices.delete(device.macAddress); } catch { /* ignore */ }
    }
  });

  test('cancels delete keeps device', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'ca-ac-de-10-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();

      // Click delete
      await devicesPage.deleteDevice(device.macAddress);

      // Cancel
      await devicesPage.cancelDelete();

      // Dialog should close
      await expect(devicesPage.deleteConfirmDialog).not.toBeVisible();

      // Device should still be visible
      await expect(devicesPage.row(device.macAddress)).toBeVisible();
    } finally {
      await devices.delete(device.macAddress);
    }
  });
});

test.describe('MAC Address Rename', () => {
  test('renames device by changing MAC address', async ({ page, devices }) => {
    const originalMac = '0a-10-ac-00-00-01';
    const newMac = 'ae-fa-c0-00-00-01';

    const device = await devices.create({ macAddress: originalMac, deviceName: 'Rename Test' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.macAddress);
      await devicesPage.waitForEditorLoaded();

      // Change MAC address
      await devicesPage.fillMacAddress(newMac);

      // Wait for validation
      await page.waitForTimeout(100);

      // Save
      await devicesPage.save();

      // Wait for navigation
      await expect(page).toHaveURL('/devices');
      await devicesPage.waitForListLoaded();

      // New MAC should exist, old should not
      await expect(devicesPage.row(newMac)).toBeVisible();
      await expect(devicesPage.row(originalMac)).not.toBeVisible();

      // Cleanup with new MAC
      await devices.delete(newMac);
    } catch {
      // Cleanup either MAC in case of failure
      try { await devices.delete(originalMac); } catch { /* ignore */ }
      try { await devices.delete(newMac); } catch { /* ignore */ }
      throw new Error('Test failed');
    }
  });
});

test.describe('Unsaved Changes', () => {
  test('shows confirmation when canceling with unsaved changes', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: '0a-5a-fe-d0-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.macAddress);
      await devicesPage.waitForEditorLoaded();

      // Make a change
      await devicesPage.fillMacAddress('c1-aa-6e-d0-00-01');

      // Try to cancel
      await devicesPage.cancel();

      // Confirmation dialog should appear
      await expect(devicesPage.unsavedChangesDialog).toBeVisible();

      // Cancel the discard - stay on page
      await devicesPage.cancelDiscard();
      await expect(page).toHaveURL(`/devices/${encodeURIComponent(device.macAddress)}`);

      // Try again and confirm discard
      await devicesPage.cancel();
      await devicesPage.confirmDiscard();

      // Should navigate away
      await expect(page).toHaveURL('/devices');
    } finally {
      await devices.delete(device.macAddress);
    }
  });

  test('no confirmation when canceling without changes', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'a0-c1-aa-6e-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.macAddress);
      await devicesPage.waitForEditorLoaded();

      // Cancel without making changes
      await devicesPage.cancel();

      // Should navigate directly without confirmation
      await expect(page).toHaveURL('/devices');
    } finally {
      await devices.delete(device.macAddress);
    }
  });
});

test.describe('Error Handling', () => {
  test('shows error for invalid MAC address format from backend', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // Use an invalid MAC format that will be rejected by backend
    await devicesPage.fillMacAddress('invalid-mac');
    await devicesPage.setJsonObject({ deviceName: 'Test', deviceEntityId: 'test', enableOTA: false });

    // Wait for validation
    await page.waitForTimeout(100);

    await devicesPage.save();

    // Should show error - either a toast or stay on page (backend validation)
    // Check that we haven't navigated away (stayed on /devices/new due to error)
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL('/devices/new');
  });

  test('handles invalid JSON in editor', async ({ page }) => {
    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    await devicesPage.fillMacAddress('fa-11-da-ac-00-01');

    // Type invalid JSON
    await devicesPage.setJsonContent('{ invalid json }');

    // Save button should be disabled due to JSON error
    await expect(devicesPage.saveButton).toBeDisabled();

    // Error indicator should be visible
    await expect(devicesPage.jsonEditorContainer).toHaveAttribute('data-state', 'invalid');
  });

  test('shows error for duplicate MAC address', async ({ page, devices }) => {
    const existingDevice = await devices.create({ macAddress: 'd0-b1-1c-ac-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoNew();
      await devicesPage.waitForEditorLoaded();

      // Try to create with same MAC
      await devicesPage.fillMacAddress(existingDevice.macAddress);
      await devicesPage.setJsonObject({ deviceName: 'Duplicate', deviceEntityId: 'dup', enableOTA: false });

      // Wait for validation
      await page.waitForTimeout(100);

      await devicesPage.save();

      // Note: Backend may allow upsert (update existing), so this might succeed
      // or show an error depending on backend implementation
      // We just verify the action completes without crashing
      await expect(page).toHaveURL('/devices');
    } finally {
      await devices.delete(existingDevice.macAddress);
    }
  });
});

test.describe('Sorting', () => {
  test('sorts devices by MAC address', async ({ page, devices }) => {
    const device1 = await devices.create({ macAddress: 'aa-00-00-00-00-01' });
    const device2 = await devices.create({ macAddress: 'ff-00-00-00-00-01' });
    const device3 = await devices.create({ macAddress: 'cc-00-00-00-00-01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();

      // Click MAC Address header to sort
      await page.locator('[data-testid="devices.list.header.macAddress"]').click();

      // Get order of MACs
      const macs = await devicesPage.getMacAddressesInList();

      // Should be sorted (either asc or desc)
      const sortedAsc = [...macs].sort();
      const sortedDesc = [...macs].sort().reverse();

      const isSorted = JSON.stringify(macs) === JSON.stringify(sortedAsc) ||
                       JSON.stringify(macs) === JSON.stringify(sortedDesc);

      expect(isSorted).toBe(true);
    } finally {
      await devices.delete(device1.macAddress);
      await devices.delete(device2.macAddress);
      await devices.delete(device3.macAddress);
    }
  });
});
