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

  async gotoEdit(deviceId: number) {
    await this.page.goto(`/devices/${deviceId}`);
  }

  async gotoDuplicate(deviceId: number) {
    await this.page.goto(`/devices/${deviceId}/duplicate`);
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

  /**
   * Get a row by device key
   */
  rowByKey(key: string): Locator {
    return this.page.locator(`[data-testid="devices.list.row"][data-device-key="${key}"]`);
  }

  /**
   * Get a row by device ID
   */
  rowById(id: number): Locator {
    return this.page.locator(`[data-testid="devices.list.row"][data-device-id="${id}"]`);
  }

  rowByIndex(index: number): Locator {
    return this.page.locator('[data-testid="devices.list.row"]').nth(index);
  }

  // Locators - Editor
  get editor(): Locator {
    return this.page.locator('[data-testid="devices.editor"]');
  }

  get keyDisplay(): Locator {
    return this.page.locator('[data-testid="devices.editor.key-display"]');
  }

  get modelDisplay(): Locator {
    return this.page.locator('[data-testid="devices.editor.model-display"]');
  }

  get modelSelect(): Locator {
    return this.page.locator('[data-testid="devices.editor.model-select"]');
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

  get provisionDeviceButton(): Locator {
    return this.page.locator('[data-testid="devices.editor.provision-device"]');
  }

  // Locators - Provision Modal
  get provisionModal(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal"]');
  }

  get provisionModalProgressBar(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.progress-bar"]');
  }

  get provisionModalStatusMessage(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.status-message"]');
  }

  get provisionModalErrorMessage(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.error-message"]');
  }

  get provisionModalConnectButton(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.connect-button"]');
  }

  get provisionModalCloseButton(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.close-button"]');
  }

  get provisionModalRetryButton(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.retry-button"]');
  }

  get provisionModalCloseConfirmDialog(): Locator {
    return this.page.locator('[data-testid="devices.provision-modal.close-confirm-dialog"]');
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

  async editDeviceByKey(key: string) {
    await this.rowByKey(key).locator('[data-testid="devices.list.row.edit-button"]').click();
  }

  async editDeviceById(id: number) {
    await this.rowById(id).locator('[data-testid="devices.list.row.edit-button"]').click();
  }

  async deleteDeviceByKey(key: string) {
    await this.rowByKey(key).locator('[data-testid="devices.list.row.delete-button"]').click();
  }

  async deleteDeviceById(id: number) {
    await this.rowById(id).locator('[data-testid="devices.list.row.delete-button"]').click();
  }

  async confirmDelete() {
    await this.deleteConfirmDialog.locator('button:has-text("Delete")').click();
  }

  async cancelDelete() {
    await this.deleteConfirmDialog.locator('button:has-text("Cancel")').click();
  }

  // Actions - Editor
  async selectModel(modelName: string) {
    await this.modelSelect.click();
    // Click the option that contains the model name
    await this.page.locator(`[role="option"]:has-text("${modelName}")`).click();
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

  // Actions - Provisioning
  async openProvisionModal() {
    await this.provisionDeviceButton.click();
    await this.provisionModal.waitFor({ state: 'visible' });
  }

  async closeProvisionModal() {
    await this.provisionModalCloseButton.click();
    await this.provisionModal.waitFor({ state: 'hidden' });
  }

  async startProvisioning() {
    await this.provisionModalConnectButton.click();
  }

  async retryProvisioning() {
    await this.provisionModalRetryButton.click();
  }

  async confirmCloseProvisioning() {
    await this.provisionModalCloseConfirmDialog.locator('button:has-text("Yes, Cancel")').click();
  }

  async cancelCloseProvisioning() {
    await this.provisionModalCloseConfirmDialog.locator('button:has-text("Continue")').click();
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

  async getDeviceKeysInList(): Promise<string[]> {
    const rows = await this.rows.all();
    const keys: string[] = [];
    for (const row of rows) {
      const key = await row.getAttribute('data-device-key');
      if (key) keys.push(key);
    }
    return keys;
  }

  /**
   * Wait for provisioning to complete (success or error state)
   */
  async waitForProvisioningComplete(): Promise<void> {
    // Wait for either success message or error message to appear
    await Promise.race([
      this.page.locator('text=Provisioning Complete').waitFor({ state: 'visible', timeout: 30000 }),
      this.page.locator('text=Provisioning Failed').waitFor({ state: 'visible', timeout: 30000 }),
    ]);
  }

  /**
   * Wait for provisioning success state
   */
  async waitForProvisioningSuccess(): Promise<void> {
    await this.page.locator('text=Provisioning Complete').waitFor({ state: 'visible', timeout: 30000 });
  }

  /**
   * Wait for provisioning error state
   */
  async waitForProvisioningError(): Promise<void> {
    await this.page.locator('text=Provisioning Failed').waitFor({ state: 'visible', timeout: 30000 });
  }
}
