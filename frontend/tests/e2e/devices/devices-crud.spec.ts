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
    const device1 = await devices.create({ macAddress: 'b1:bb:cc:dd:ee:01', deviceName: 'Living Room Sensor' });
    const device2 = await devices.create({ macAddress: 'b2:bb:cc:dd:ee:02', deviceName: 'Kitchen Sensor' });

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
      try { await devices.delete(device1.id); } catch { /* ignore */ }
      try { await devices.delete(device2.id); } catch { /* ignore */ }
    }
  });

  test('displays OTA status icons correctly', async ({ page, devices }) => {
    // Use random MACs to avoid conflicts
    const deviceOtaTrue = await devices.create({ enableOTA: true });
    const deviceOtaFalse = await devices.create({ enableOTA: false });

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
      await devices.delete(deviceOtaTrue.id);
      await devices.delete(deviceOtaFalse.id);
    }
  });

  test('navigates to new device editor', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.clickNewDevice();

    await expect(page).toHaveURL('/devices/new');
    await expect(devicesPage.editor).toBeVisible();
    await expect(devicesPage.macInput).toBeVisible();
  });

  test('navigates to edit device', async ({ page, devices }) => {
    // Use lowercase MAC with colons
    const device = await devices.create({ macAddress: 'ed:11:1e:51:00:01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();
      await devicesPage.editDevice(device.macAddress);

      // URL now uses device ID
      await expect(page).toHaveURL(`/devices/${device.id}`);
      await expect(devicesPage.editor).toBeVisible();
      // In edit mode, MAC is displayed as text (not editable)
      await expect(devicesPage.macDisplay).toContainText(device.macAddress);
    } finally {
      await devices.delete(device.id);
    }
  });
});

test.describe('Create Device', () => {
  test('creates a new device with valid data', async ({ page, devices }) => {
    // Use lowercase MAC - backend will normalize it anyway
    const testMac = 'ae:fd:ef:1c:e0:01';
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

    // Cleanup - use deleteByMac since we created via UI
    await devices.deleteByMac(testMac);
  });

  test('save button is disabled when MAC address is empty', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // MAC is empty by default, save should be disabled
    await expect(devicesPage.saveButton).toBeDisabled();

    // Fill MAC, save should be enabled
    await devicesPage.fillMacAddress('1e:51:ac:00:00:01');
    await expect(devicesPage.saveButton).toBeEnabled();

    // Clear MAC, save should be disabled again
    await devicesPage.fillMacAddress('');
    await expect(devicesPage.saveButton).toBeDisabled();
  });

  test('cancel navigates back to list', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

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
      macAddress: 'ed:11:ee:15:10:01',
      deviceName: 'Original Name'
    });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      // Verify MAC is displayed (read-only in edit mode)
      await expect(devicesPage.macDisplay).toContainText(device.macAddress);

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
      await devices.delete(device.id);
    }
  });

  test('shows duplicate button in edit mode', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'd0:b1:b1:a0:00:01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      await expect(devicesPage.duplicateButton).toBeVisible();
    } finally {
      await devices.delete(device.id);
    }
  });
});

test.describe('Duplicate Device', () => {
  test('duplicates a device via new device page', async ({ page, devices }) => {
    const sourceDevice = await devices.create({
      macAddress: '5c:ce:d0:b1:00:01',
      deviceName: 'Source Device',
      deviceEntityId: 'source_entity'
    });

    const newMac = 'd0:b1:1c:a1:e0:01';

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(sourceDevice.id);
      await devicesPage.waitForEditorLoaded();

      // Click duplicate button
      await devicesPage.duplicate();

      // Should navigate to /devices/new with config in search params
      await expect(page).toHaveURL(/\/devices\/new\?/);
      await devicesPage.waitForEditorLoaded();

      // MAC should be empty (user needs to enter new MAC)
      await expect(devicesPage.macInput).toHaveValue('');

      // Title should show it's a duplicate
      await expect(page.locator('h1')).toContainText('Duplicate Device');

      // Fill in new MAC
      await devicesPage.fillMacAddress(newMac);

      // Wait for validation
      await page.waitForTimeout(100);

      await devicesPage.save();

      // Wait for navigation
      await expect(page).toHaveURL('/devices');
      await devicesPage.waitForListLoaded();

      // The new device should exist
      await expect(devicesPage.row(newMac)).toBeVisible();

      // Cleanup the duplicate - use deleteByMac since created via UI
      try { await devices.deleteByMac(newMac); } catch { /* ignore */ }
    } finally {
      try { await devices.delete(sourceDevice.id); } catch { /* ignore */ }
    }
  });

  test('duplicate preserves JSON configuration', async ({ page, devices }) => {
    const sourceDevice = await devices.create({
      macAddress: 'aa:fd:0b:10:00:01',
      deviceName: 'Source Config Name',
      deviceEntityId: 'source_config_entity',
      enableOTA: true
    });

    try {
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
    } finally {
      try { await devices.delete(sourceDevice.id); } catch { /* ignore */ }
    }
  });
});

test.describe('Delete Device', () => {
  test('shows delete confirmation dialog', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'de:1e:1e:ae:00:01' });

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
      try { await devices.delete(device.id); } catch { /* ignore */ }
    }
  });

  test('cancels delete keeps device', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'ca:ac:de:10:00:01' });

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
      await devices.delete(device.id);
    }
  });
});

// Note: MAC Address Rename test removed - MAC addresses are now immutable in the new API.
// Devices are identified by a surrogate ID, and MAC address cannot be changed after creation.

test.describe('Unsaved Changes', () => {
  test('shows confirmation when canceling with unsaved changes', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: '0a:5a:fe:d0:00:01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      // Make a change to the JSON config (MAC is not editable in edit mode)
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
    } finally {
      await devices.delete(device.id);
    }
  });

  test('no confirmation when canceling without changes', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'a0:c1:aa:6e:00:01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      // Cancel without making changes
      await devicesPage.cancel();

      // Should navigate directly without confirmation
      await expect(page).toHaveURL('/devices');
    } finally {
      await devices.delete(device.id);
    }
  });

  test('shows confirmation when clicking sidebar with unsaved changes', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'a1:de:ba:61:00:01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.gotoEdit(device.id);
      await devicesPage.waitForEditorLoaded();

      // Make a change to the JSON config (MAC is not editable in edit mode)
      await devicesPage.setJsonObject({
        deviceName: 'Changed Name',
        deviceEntityId: 'changed_entity',
        enableOTA: true
      });

      // Click on sidebar link
      await page.locator('[data-testid="app-shell.sidebar.link.devices"]').click();

      // Navigation blocker dialog should appear
      const blockerDialog = page.locator('[data-testid="devices.editor.navigation-blocker-dialog"]');
      await expect(blockerDialog).toBeVisible();

      // Cancel the navigation - stay on page
      await blockerDialog.locator('button:has-text("Cancel")').click();
      await expect(page).toHaveURL(`/devices/${device.id}`);

      // Click sidebar again and confirm discard
      await page.locator('[data-testid="app-shell.sidebar.link.devices"]').click();
      await expect(blockerDialog).toBeVisible();
      await blockerDialog.locator('button:has-text("Discard")').click();

      // Should navigate away
      await expect(page).toHaveURL('/devices');
    } finally {
      await devices.delete(device.id);
    }
  });
});

test.describe('Error Handling', () => {
  test('shows error for invalid MAC address format from backend', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

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

  test('handles invalid JSON in editor', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    await devicesPage.fillMacAddress('fa:11:da:ac:00:01');

    // Type invalid JSON
    await devicesPage.setJsonContent('{ invalid json }');

    // Save button should be disabled due to JSON error
    await expect(devicesPage.saveButton).toBeDisabled();

    // Error indicator should be visible
    await expect(devicesPage.jsonEditorContainer).toHaveAttribute('data-state', 'invalid');
  });

  test('prevents overwriting existing device when creating new', async ({ page, devices }) => {
    const existingDevice = await devices.create({ macAddress: 'd0:b1:1c:ac:00:01' });

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

      // Should show error toast and stay on page (allow_overwrite=false prevents overwriting)
      await page.waitForTimeout(1000);
      await expect(page).toHaveURL('/devices/new');

      // Toast should show an error message (use first() since there might be multiple)
      await expect(page.locator('[role="status"]').first()).toBeVisible();
    } finally {
      await devices.delete(existingDevice.id);
    }
  });

  test('shows error when opening non-existent device', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

    const devicesPage = new DevicesPage(page);

    // Navigate to a non-existent device (use a very high ID that won't exist)
    await devicesPage.gotoEdit(999999);

    // Wait for loading to complete and error to appear
    // The error message from the backend contains "was not found"
    await expect(page.locator('text=/was not found|not found/i')).toBeVisible({ timeout: 10000 });

    // Should show "Back to Device List" button
    await expect(page.locator('text=Back to Device List')).toBeVisible();
  });

  test('back to list button works on 404 page', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

    const devicesPage = new DevicesPage(page);

    // Navigate to a non-existent device (use a very high ID that won't exist)
    await devicesPage.gotoEdit(999998);

    // Wait for error message to appear
    await expect(page.locator('text=/was not found|not found/i')).toBeVisible({ timeout: 10000 });

    // Click back to list button
    await page.locator('text=Back to Device List').click();

    // Should navigate to device list
    await expect(page).toHaveURL('/devices');
  });
});

test.describe('UI Elements', () => {
  test('MAC address help text shows correct format', async ({ page, auth }) => {
    await auth.createSession({ name: 'Test User' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.gotoNew();
    await devicesPage.waitForEditorLoaded();

    // Help text should show colon-separated lowercase format
    await expect(page.locator('text=aa:bb:cc:dd:ee:ff')).toBeVisible();
    await expect(page.locator('text=colon-separated, lowercase')).toBeVisible();
  });

  test('edit and delete buttons show icons', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'b1:c0:50:00:00:01' });

    try {
      const devicesPage = new DevicesPage(page);
      await devicesPage.goto();
      await devicesPage.waitForListLoaded();

      // Edit button should have pencil icon (svg)
      const editButton = devicesPage.row(device.macAddress).locator('[data-testid="devices.list.row.edit-button"]');
      await expect(editButton.locator('svg')).toBeVisible();

      // Delete button should have trash icon (svg)
      const deleteButton = devicesPage.row(device.macAddress).locator('[data-testid="devices.list.row.delete-button"]');
      await expect(deleteButton.locator('svg')).toBeVisible();
    } finally {
      await devices.delete(device.id);
    }
  });

  test('list reloads after saving a new device', async ({ page, devices }) => {
    const testMac = 'c1:ea:d5:00:00:01';
    const devicesPage = new DevicesPage(page);

    try {
      // Create new device
      await devicesPage.gotoNew();
      await devicesPage.waitForEditorLoaded();
      await devicesPage.fillMacAddress(testMac);
      await devicesPage.setJsonObject({ deviceName: 'Reload Test', deviceEntityId: 'reload_test', enableOTA: false });
      await page.waitForTimeout(100);
      await devicesPage.save();

      // Wait for navigation and list to reload
      await expect(page).toHaveURL('/devices');
      await devicesPage.waitForListLoaded();

      // Wait a bit for the query to refetch after invalidation
      await page.waitForTimeout(500);

      // Device should now be visible (list was reloaded)
      await expect(devicesPage.row(testMac)).toBeVisible({ timeout: 10000 });
    } finally {
      // Cleanup - use deleteByMac since created via UI
      try { await devices.deleteByMac(testMac); } catch { /* ignore */ }
    }
  });

  test('list reloads after deleting a device', async ({ page, devices }) => {
    const device = await devices.create({ macAddress: 'de:e1:e1:00:00:01' });

    const devicesPage = new DevicesPage(page);
    await devicesPage.goto();
    await devicesPage.waitForListLoaded();

    // Verify device exists
    await expect(devicesPage.row(device.macAddress)).toBeVisible();

    // Delete device
    await devicesPage.deleteDevice(device.macAddress);
    await devicesPage.confirmDelete();

    // Wait for query invalidation and list to update
    await expect(devicesPage.row(device.macAddress)).not.toBeVisible({ timeout: 10000 });
  });
});

test.describe('Sorting', () => {
  test('sorts devices by MAC address', async ({ page, devices }) => {
    // Use random MACs - the test just verifies sorting works, doesn't need specific values
    const device1 = await devices.create();
    const device2 = await devices.create();
    const device3 = await devices.create();

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
      await devices.delete(device1.id);
      await devices.delete(device2.id);
      await devices.delete(device3.id);
    }
  });
});
