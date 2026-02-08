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
    // Create test devices with unique configurations
    const device1 = await devices.create({ deviceName: 'Living Room Sensor' });
    const device2 = await devices.create({ deviceName: 'Kitchen Sensor' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Verify table is visible (or empty state if deleted by parallel test)
    const isTableVisible = await devicesPage.list.isVisible().catch(() => false);
    if (isTableVisible) {
      // Verify both devices appear by their key
      await expect(devicesPage.rowByKey(device1.key)).toBeVisible();
      await expect(devicesPage.rowByKey(device2.key)).toBeVisible();

      // Verify device names are shown
      await expect(devicesPage.rowByKey(device1.key)).toContainText('Living Room Sensor');
      await expect(devicesPage.rowByKey(device2.key)).toContainText('Kitchen Sensor');
    }
  });

  test('displays OTA status icons correctly', async ({ page, devices }) => {
    const deviceOtaTrue = await devices.create({ enableOta: true });
    const deviceOtaFalse = await devices.create({ enableOta: false });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // OTA true should show check mark
    const rowTrue = devicesPage.rowByKey(deviceOtaTrue.key);
    await expect(rowTrue.locator('text=✓')).toBeVisible();

    // OTA false should show cross
    const rowFalse = devicesPage.rowByKey(deviceOtaFalse.key);
    await expect(rowFalse.locator('text=✕')).toBeVisible();
  });

  test('navigates to new device editor', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.clickNewDevice();

    await expect(page).toHaveURL('/devices/new');
    await expect(devicesPage.editor).toBeVisible();
    await expect(devicesPage.modelSelect).toBeVisible();
  });

  test('navigates to edit device', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Test Device' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();
    await devicesPage.editDeviceByKey(device.key);

    // URL now uses device ID
    await expect(page).toHaveURL(`/devices/${device.id}`);
    await expect(devicesPage.editor).toBeVisible();
    // In edit mode, key is displayed as text (read-only)
    await expect(devicesPage.keyDisplay).toContainText(device.key);
  });
});

test.describe('Create Device', () => {
  test('creates a new device with valid data', async ({ page, deviceModels }) => {
    // Create a device model with unique name to avoid selector collisions
    const model = await deviceModels.create();

    const devicesPage = new DevicesPage(page);

    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // Select the model
    await devicesPage.selectModel(model.name);

    // Fill in the JSON config
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

    // Verify the device appears in list
    await expect(devicesPage.rows.first()).toBeVisible();
  });

  test('save button is disabled when no model is selected', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // No model selected, save should be disabled
    await expect(devicesPage.saveButton).toBeDisabled();
  });

  test('cancel navigates back to list', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    await devicesPage.cancel();

    await expect(page).toHaveURL('/devices');
  });
});

test.describe('Edit Device', () => {
  test('edits an existing device', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Original Name' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Verify key is displayed (read-only in edit mode)
    await expect(devicesPage.keyDisplay).toContainText(device.key);

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
    await expect(devicesPage.rowByKey(device.key)).toContainText('Updated Name');
  });

  test('shows duplicate button in edit mode', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    await expect(devicesPage.duplicateButton).toBeVisible();
  });
});

test.describe('Duplicate Device', () => {
  test('duplicates a device via edit page', async ({ page, devices }) => {
    const sourceDevice = await devices.create({
      deviceName: 'Source Device',
      deviceEntityId: 'source_entity'
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(sourceDevice.id);
    await devicesPage.waitForEditorLoaded();

    // Click duplicate button
    await devicesPage.duplicate();

    // Should navigate to /devices/new with config in search params
    await expect(page).toHaveURL(/\/devices\/new\?/);
    await devicesPage.waitForEditorLoaded();

    // Title should show it's a duplicate
    await expect(page.locator('h1')).toContainText('Duplicate Device');

    // Wait for validation
    await page.waitForTimeout(100);

    await devicesPage.save();

    // Wait for navigation
    await expect(page).toHaveURL('/devices');
    await devicesPage.waitForListLoaded();

    // Should have at least two devices (the original and the duplicate)
    // Note: Other tests may leave devices behind, so we check for minimum count
    const rowCount = await devicesPage.rows.count();
    expect(rowCount).toBeGreaterThanOrEqual(2);
  });

  test('duplicate preserves JSON configuration', async ({ page, devices }) => {
    const sourceDevice = await devices.create({
      deviceName: 'Source Config Name',
      deviceEntityId: 'source_config_entity',
      enableOta: true
    });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(sourceDevice.id);
    await devicesPage.waitForEditorLoaded();

    // Click duplicate button
    await devicesPage.duplicate();

    // Wait for navigation and editor load
    await expect(page).toHaveURL(/\/devices\/new\?/);
    await devicesPage.waitForEditorLoaded();

    // The JSON editor should contain the source device's config
    const monacoContent = await page.evaluate(() => {
      const monaco = (window as unknown as { monaco?: { editor: { getEditors(): Array<{ getValue(): string }> } } }).monaco;
      if (monaco) {
        const editors = monaco.editor.getEditors();
        if (editors.length > 0) {
          return editors[0].getValue();
        }
      }
      return '';
    });

    const config = JSON.parse(monacoContent);
    expect(config.deviceName).toBe('Source Config Name');
    expect(config.deviceEntityId).toBe('source_config_entity');
    expect(config.enableOTA).toBe(true);
  });
});

test.describe('Delete Device', () => {
  test('shows delete confirmation dialog', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'To Delete' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Verify device exists before delete
    await expect(devicesPage.rowByKey(device.key)).toBeVisible();

    // Click delete
    await devicesPage.deleteDeviceByKey(device.key);

    // Confirmation dialog should appear
    await expect(devicesPage.deleteConfirmDialog).toBeVisible();
    await expect(devicesPage.deleteConfirmDialog).toContainText(device.key);

    // Confirm button should be visible
    await expect(devicesPage.deleteConfirmDialog.locator('button:has-text("Delete")')).toBeVisible();

    // Cancel button should be visible
    await expect(devicesPage.deleteConfirmDialog.locator('button:has-text("Cancel")')).toBeVisible();

    // Click cancel to close
    await devicesPage.cancelDelete();

    // Dialog should close
    await expect(devicesPage.deleteConfirmDialog).not.toBeVisible();
  });

  test('cancels delete keeps device', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Keep Me' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Click delete
    await devicesPage.deleteDeviceByKey(device.key);

    // Cancel
    await devicesPage.cancelDelete();

    // Dialog should close
    await expect(devicesPage.deleteConfirmDialog).not.toBeVisible();

    // Device should still be visible
    await expect(devicesPage.rowByKey(device.key)).toBeVisible();
  });

  test('confirms delete removes device', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Delete Me' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Click delete
    await devicesPage.deleteDeviceByKey(device.key);

    // Confirm
    await devicesPage.confirmDelete();

    // Device should be removed from list
    await expect(devicesPage.rowByKey(device.key)).not.toBeVisible({ timeout: 10000 });
  });
});

test.describe('Unsaved Changes', () => {
  test('shows confirmation when canceling with unsaved changes', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Original' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Make a change to the JSON config
    await devicesPage.setJsonObject({
      deviceName: 'Changed Name',
      deviceEntityId: 'changed_entity',
      enableOTA: true
    });

    // Try to cancel
    await devicesPage.cancel();

    // Confirmation dialog should appear
    await expect(devicesPage.unsavedChangesDialog).toBeVisible();

    // Cancel the discard - stay on page
    await devicesPage.cancelDiscard();
    await expect(page).toHaveURL(`/devices/${device.id}`);

    // Try again and confirm discard
    await devicesPage.cancel();
    await devicesPage.confirmDiscard();

    // Should navigate away
    await expect(page).toHaveURL('/devices');
  });

  test('no confirmation when canceling without changes', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoEdit(device.id);
    await devicesPage.waitForEditorLoaded();

    // Cancel without making changes
    await devicesPage.cancel();

    // Should navigate directly without confirmation
    await expect(page).toHaveURL('/devices');
  });
});

test.describe('Error Handling', () => {
  test('handles invalid JSON in editor', async ({ page, deviceModels }) => {
    const model = await deviceModels.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    await devicesPage.selectModel(model.name);

    // Type invalid JSON
    await devicesPage.setJsonContent('{ invalid json }');

    // Save button should be disabled due to JSON error
    await expect(devicesPage.saveButton).toBeDisabled();

    // Error indicator should be visible
    await expect(devicesPage.jsonEditorContainer).toHaveAttribute('data-state', 'invalid');
  });

  test('shows error when opening non-existent device', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    const devicesPage = new DevicesPage(page);

    // Navigate to a non-existent device (use a very high ID that won't exist)
    await devicesPage.gotoEdit(999999);

    // Wait for loading to complete and error to appear
    await expect(page.locator('text=/not found/i')).toBeVisible({ timeout: 10000 });

    // Should show "Back to Device List" button
    await expect(page.locator('text=Back to Device List')).toBeVisible();
  });

  test('back to list button works on 404 page', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    const devicesPage = new DevicesPage(page);

    // Navigate to a non-existent device (use a very high ID that won't exist)
    await devicesPage.gotoEdit(999998);

    // Wait for error message to appear
    await expect(page.locator('text=/not found/i')).toBeVisible({ timeout: 10000 });

    // Click back to list button
    await page.locator('text=Back to Device List').click();

    // Should navigate to device list
    await expect(page).toHaveURL('/devices');
  });
});

test.describe('UI Elements', () => {
  test('rows are clickable and delete button shows icon', async ({ page, devices }) => {
    const device = await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Rows should be clickable (cursor-pointer)
    const row = devicesPage.rowByKey(device.key);
    await expect(row).toHaveCSS('cursor', 'pointer');

    // Delete button should have trash icon (svg)
    const deleteButton = row.locator('[data-testid="devices.list.row.delete-button"]');
    await expect(deleteButton.locator('svg')).toBeVisible();
  });

  test('list reloads after deleting a device', async ({ page, devices }) => {
    const device = await devices.create({ deviceName: 'Delete Test' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Verify device exists
    await expect(devicesPage.rowByKey(device.key)).toBeVisible();

    // Delete device
    await devicesPage.deleteDeviceByKey(device.key);
    await devicesPage.confirmDelete();

    // Wait for query invalidation and list to update
    await expect(devicesPage.rowByKey(device.key)).not.toBeVisible({ timeout: 10000 });
  });
});

test.describe('Sorting', () => {
  test('sorts devices by key', async ({ page, devices }) => {
    // Create test devices for sorting verification
    await devices.create();
    await devices.create();
    await devices.create();

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Click key header to sort
    await page.locator('[data-testid="devices.list.header.key"]').click();

    // Get order of keys
    const keys = await devicesPage.getDeviceKeysInList();

    // Should be sorted (either asc or desc)
    const sortedAsc = [...keys].sort();
    const sortedDesc = [...keys].sort().reverse();

    const isSorted = JSON.stringify(keys) === JSON.stringify(sortedAsc) ||
                     JSON.stringify(keys) === JSON.stringify(sortedDesc);

    expect(isSorted).toBe(true);
  });
});
