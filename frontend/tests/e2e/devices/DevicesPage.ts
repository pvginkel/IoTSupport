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

  async gotoLogs(deviceId: number) {
    await this.page.goto(`/devices/${deviceId}/logs`);
  }

  async gotoCoredumps(deviceId: number) {
    await this.page.goto(`/devices/${deviceId}/coredumps`);
  }

  async gotoCoredumpDetail(deviceId: number, coredumpId: number) {
    await this.page.goto(`/devices/${deviceId}/coredumps/${coredumpId}`);
  }

  // --- Tab Navigation ---
  get tabConfiguration(): Locator {
    return this.page.locator('[data-testid="devices.detail.tab.configuration"]');
  }

  get tabLogs(): Locator {
    return this.page.locator('[data-testid="devices.detail.tab.logs"]');
  }

  get tabCoredumps(): Locator {
    return this.page.locator('[data-testid="devices.detail.tab.coredumps"]');
  }

  get detailHeader(): Locator {
    return this.page.locator('[data-testid="devices.detail.header"]');
  }

  get detailTabs(): Locator {
    return this.page.locator('[data-testid="devices.detail.tabs"]');
  }

  // Header identity locators
  get headerDeviceKey(): Locator {
    return this.page.locator('[data-testid="devices.detail.header.device-key"]');
  }

  get headerDeviceModel(): Locator {
    return this.page.locator('[data-testid="devices.detail.header.device-model"]');
  }

  get headerRotationBadge(): Locator {
    return this.page.locator('[data-testid="devices.detail.header.rotation-badge"]');
  }

  get headerOtaBadge(): Locator {
    return this.page.locator('[data-testid="devices.detail.header.ota-badge"]');
  }

  async clickTab(tab: 'configuration' | 'logs' | 'coredumps') {
    switch (tab) {
      case 'configuration':
        await this.tabConfiguration.click();
        break;
      case 'logs':
        await this.tabLogs.click();
        break;
      case 'coredumps':
        await this.tabCoredumps.click();
        break;
    }
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

  rowByKey(key: string): Locator {
    return this.page.locator(`[data-testid="devices.list.row"][data-device-key="${key}"]`);
  }

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

  // Locators - Device Logs Viewer
  get logsViewer(): Locator {
    return this.page.locator('[data-testid="devices.logs.viewer"]');
  }

  get logsStreamingStatus(): Locator {
    return this.page.locator('[data-testid="devices.logs.streaming-status"]');
  }

  get logsContainer(): Locator {
    return this.page.locator('[data-testid="devices.logs.container"]');
  }

  get logsEntries(): Locator {
    return this.page.locator('[data-testid="devices.logs.entry"]');
  }

  get logsEmptyState(): Locator {
    return this.page.locator('[data-testid="devices.logs.empty"]');
  }

  // Locators - Coredump Table
  get coredumpTable(): Locator {
    return this.page.locator('[data-testid="coredumps.table"]');
  }

  get coredumpTableEmpty(): Locator {
    return this.page.locator('[data-testid="coredumps.table.empty"]');
  }

  get coredumpTableLoading(): Locator {
    return this.page.locator('[data-testid="coredumps.table.loading"]');
  }

  get coredumpTableError(): Locator {
    return this.page.locator('[data-testid="coredumps.table.error"]');
  }

  get coredumpRows(): Locator {
    return this.page.locator('[data-testid="coredumps.table.row"]');
  }

  coredumpRowById(coredumpId: number): Locator {
    return this.page.locator(`[data-testid="coredumps.table.row"][data-coredump-id="${coredumpId}"]`);
  }

  get coredumpDeleteConfirmDialog(): Locator {
    return this.page.locator('[data-testid="coredumps.delete.confirm-dialog"]');
  }

  // Locators - Coredump Accordion
  get coredumpAccordionExpanded(): Locator {
    return this.page.locator('[data-testid="coredumps.accordion.expanded"]');
  }

  get coredumpAccordionMetadata(): Locator {
    return this.page.locator('[data-testid="coredumps.accordion.metadata"]');
  }

  get coredumpAccordionEditor(): Locator {
    return this.page.locator('[data-testid="coredumps.accordion.editor"]');
  }

  get coredumpAccordionNoOutput(): Locator {
    return this.page.locator('[data-testid="coredumps.accordion.no-output"]');
  }

  // Locators - Coredump Detail Page (legacy - kept for backward compat)
  get coredumpDetail(): Locator {
    return this.page.locator('[data-testid="coredumps.detail"]');
  }

  get coredumpDetailMetadata(): Locator {
    return this.page.locator('[data-testid="coredumps.detail.metadata"]');
  }

  get coredumpDetailEditor(): Locator {
    return this.page.locator('[data-testid="coredumps.detail.editor"]');
  }

  get coredumpDetailNoOutput(): Locator {
    return this.page.locator('[data-testid="coredumps.detail.no-output"]');
  }

  get coredumpDetailDownload(): Locator {
    return this.page.locator('[data-testid="coredumps.detail.download"]');
  }

  get coredumpDetailBack(): Locator {
    return this.page.locator('[data-testid="coredumps.detail.back"]');
  }

  get coredumpDetailError(): Locator {
    return this.page.locator('[data-testid="coredumps.detail.error"]');
  }

  // Locators - Device List Column Header
  get lastCoredumpAtHeader(): Locator {
    return this.page.locator('[data-testid="devices.list.header.lastCoredumpAt"]');
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
    await this.rowByKey(key).click();
  }

  async editDeviceById(id: number) {
    await this.rowById(id).click();
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
    await this.page.locator(`[role="option"]:has-text("${modelName}")`).click();
  }

  async setJsonContent(content: string) {
    await this.monacoEditor.waitFor({ state: 'visible' });

    await this.page.evaluate((newContent) => {
      const monaco = (window as unknown as { monaco?: { editor: { getEditors(): Array<{ setValue(value: string): void }> } } }).monaco;
      if (monaco) {
        const editors = monaco.editor.getEditors();
        if (editors.length > 0) {
          editors[0].setValue(newContent);
        }
      }
    }, content);

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
    await Promise.race([
      this.list.waitFor({ state: 'visible', timeout: 10000 }),
      this.emptyState.waitFor({ state: 'visible', timeout: 10000 }),
    ]);
  }

  /** Wait for the configuration tab editor to be ready */
  async waitForEditorLoaded() {
    await this.editor.waitFor({ state: 'visible' });
    await this.monacoEditor.waitFor({ state: 'visible' });
  }

  /** Alias for waitForEditorLoaded — used in config tab context */
  async waitForConfigTabLoaded() {
    await this.waitForEditorLoaded();
  }

  /** Wait for the coredumps tab table to be ready */
  async waitForCoredumpsTabLoaded() {
    await this.coredumpTable.waitFor({ state: 'visible' });
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

  async waitForProvisioningComplete(): Promise<void> {
    await Promise.race([
      this.page.locator('text=Provisioning Complete').waitFor({ state: 'visible', timeout: 30000 }),
      this.page.locator('text=Provisioning Failed').waitFor({ state: 'visible', timeout: 30000 }),
    ]);
  }

  async waitForProvisioningSuccess(): Promise<void> {
    await this.page.locator('text=Provisioning Complete').waitFor({ state: 'visible', timeout: 30000 });
  }

  async waitForProvisioningError(): Promise<void> {
    await this.page.locator('text=Provisioning Failed').waitFor({ state: 'visible', timeout: 30000 });
  }

  // Actions - Coredump Table
  async clickCoredumpRow(coredumpId: number) {
    await this.coredumpRowById(coredumpId).click();
  }

  async deleteCoredumpById(coredumpId: number) {
    await this.coredumpRowById(coredumpId).locator('[data-testid="coredumps.table.row.delete"]').click();
  }

  async confirmCoredumpDelete() {
    await this.coredumpDeleteConfirmDialog.locator('button:has-text("Delete")').click();
  }

  async cancelCoredumpDelete() {
    await this.coredumpDeleteConfirmDialog.locator('button:has-text("Cancel")').click();
  }

  // Actions - Device Logs Viewer
  async isLogsViewerVisible(): Promise<boolean> {
    return await this.logsViewer.isVisible();
  }

  async getLogsScrollAtBottom(): Promise<boolean> {
    const value = await this.logsContainer.getAttribute('data-scroll-at-bottom');
    return value === 'true';
  }

  async getLogsEntryCount(): Promise<number> {
    return await this.logsEntries.count();
  }

  async scrollLogsToTop(): Promise<void> {
    await this.logsContainer.evaluate((el) => {
      el.scrollTop = 0;
    });
  }

  async scrollLogsToBottom(): Promise<void> {
    await this.logsContainer.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
  }
}
