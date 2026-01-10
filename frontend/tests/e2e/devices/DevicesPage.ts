import type { Page, Locator } from '@playwright/test';

export class DevicesPage {
  constructor(private page: Page) {}

  // Navigation
  async goto() {
    await this.page.goto('/devices');
  }

  async gotoNew() {
    await this.page.goto('/devices/new');
  }

  async gotoEdit(macAddress: string) {
    await this.page.goto(`/devices/${encodeURIComponent(macAddress)}`);
  }

  async gotoDuplicate(macAddress: string) {
    await this.page.goto(`/devices/${encodeURIComponent(macAddress)}/duplicate`);
  }

  // Locators - List
  get list(): Locator {
    return this.page.locator('[data-testid="devices.list.table"]');
  }

  get emptyState(): Locator {
    return this.page.locator('[data-testid="devices.list.empty"]');
  }

  get loadingState(): Locator {
    return this.page.locator('[data-testid="devices.list.loading"]');
  }

  get newDeviceButton(): Locator {
    return this.page.locator('[data-testid="devices.list.header.new-device"]');
  }

  get rows(): Locator {
    return this.page.locator('[data-testid="devices.list.row"]');
  }

  row(macAddress: string): Locator {
    return this.page.locator(`[data-testid="devices.list.row"]:has-text("${macAddress}")`);
  }

  rowByIndex(index: number): Locator {
    return this.page.locator('[data-testid="devices.list.row"]').nth(index);
  }

  // Locators - Editor
  get editor(): Locator {
    return this.page.locator('[data-testid="devices.editor"]');
  }

  get macInput(): Locator {
    return this.page.locator('[data-testid="devices.editor.mac-input"]');
  }

  get jsonEditorContainer(): Locator {
    return this.page.locator('[data-testid="devices.editor.json-editor"]');
  }

  get monacoEditor(): Locator {
    return this.page.locator('.monaco-editor');
  }

  get saveButton(): Locator {
    return this.page.locator('[data-testid="devices.editor.save"]');
  }

  get cancelButton(): Locator {
    return this.page.locator('[data-testid="devices.editor.cancel"]');
  }

  get duplicateButton(): Locator {
    return this.page.locator('[data-testid="devices.editor.duplicate"]');
  }

  // Locators - Dialogs
  get deleteConfirmDialog(): Locator {
    return this.page.locator('[data-testid="devices.delete.confirm-dialog"]');
  }

  get unsavedChangesDialog(): Locator {
    return this.page.locator('[data-testid="devices.editor.unsaved-changes-dialog"]');
  }

  // Locators - Toast
  get toast(): Locator {
    return this.page.locator('[data-testid="toast"]');
  }

  get successToast(): Locator {
    return this.page.locator('[data-testid="toast"][data-type="success"]');
  }

  get errorToast(): Locator {
    return this.page.locator('[data-testid="toast"][data-type="error"]');
  }

  // Actions - List
  async clickNewDevice() {
    await this.newDeviceButton.click();
  }

  async editDevice(macAddress: string) {
    await this.row(macAddress).locator('[data-testid="devices.list.row.edit-button"]').click();
  }

  async deleteDevice(macAddress: string) {
    await this.row(macAddress).locator('[data-testid="devices.list.row.delete-button"]').click();
  }

  async confirmDelete() {
    await this.deleteConfirmDialog.locator('button:has-text("Delete")').click();
  }

  async cancelDelete() {
    await this.deleteConfirmDialog.locator('button:has-text("Cancel")').click();
  }

  // Actions - Editor
  async fillMacAddress(macAddress: string) {
    await this.macInput.clear();
    await this.macInput.fill(macAddress);
  }

  async setJsonContent(content: string) {
    // Wait for Monaco to be ready
    await this.monacoEditor.waitFor({ state: 'visible' });

    // Use Monaco's API to set the value directly
    await this.page.evaluate((newContent) => {
      // Access Monaco's editor instance through the window
      const monaco = (window as unknown as { monaco?: { editor: { getEditors(): Array<{ setValue(value: string): void }> } } }).monaco;
      if (monaco) {
        const editors = monaco.editor.getEditors();
        if (editors.length > 0) {
          editors[0].setValue(newContent);
        }
      }
    }, content);

    // Wait for the editor to process the change
    await this.page.waitForTimeout(200);
  }

  async setJsonObject(obj: Record<string, unknown>) {
    await this.setJsonContent(JSON.stringify(obj, null, 2));
  }

  async save() {
    await this.saveButton.click();
  }

  async cancel() {
    await this.cancelButton.click();
  }

  async duplicate() {
    await this.duplicateButton.click();
  }

  async confirmDiscard() {
    await this.unsavedChangesDialog.locator('button:has-text("Discard")').click();
  }

  async cancelDiscard() {
    await this.unsavedChangesDialog.locator('button:has-text("Cancel")').click();
  }

  // Assertions helpers
  async waitForListLoaded() {
    // Wait for either the table or empty state to be visible
    await Promise.race([
      this.list.waitFor({ state: 'visible', timeout: 10000 }),
      this.emptyState.waitFor({ state: 'visible', timeout: 10000 }),
    ]);
  }

  async waitForEditorLoaded() {
    await this.editor.waitFor({ state: 'visible' });
    await this.monacoEditor.waitFor({ state: 'visible' });
  }

  async waitForSuccessToast() {
    await this.page.locator('[role="status"]:has-text("successfully")').waitFor({ state: 'visible', timeout: 5000 });
  }

  async waitForErrorToast() {
    await this.page.locator('[role="status"]').filter({ hasText: /error|failed/i }).waitFor({ state: 'visible', timeout: 5000 });
  }

  async getRowCount(): Promise<number> {
    return await this.rows.count();
  }

  async getMacAddressesInList(): Promise<string[]> {
    const rows = await this.rows.all();
    const macs: string[] = [];
    for (const row of rows) {
      const mac = await row.locator('td').first().textContent();
      if (mac) macs.push(mac);
    }
    return macs;
  }
}
