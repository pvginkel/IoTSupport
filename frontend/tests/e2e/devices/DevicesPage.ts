import type { Page, Locator } from '@playwright/test';

export class DevicesPage {
  constructor(private page: Page) {}

  // Navigation
  async goto() {
    await this.page.goto('/devices');
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

  row(macAddress: string): Locator {
    return this.page.locator(`[data-testid="devices.list.row"]:has-text("${macAddress}")`);
  }

  // Locators - Editor
  get macInput(): Locator {
    return this.page.locator('[data-testid="devices.editor.mac-input"]');
  }

  get jsonEditor(): Locator {
    return this.page.locator('[data-testid="devices.editor.json-editor"]');
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

  // Actions
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
    await this.page.locator('[data-testid="devices.delete.confirm-dialog"] button:has-text("Delete")').click();
  }

  async fillEditor(macAddress: string, config: Record<string, unknown>) {
    await this.macInput.fill(macAddress);
    // For Monaco editor, we'd need to use the editor's API or keyboard simulation
    // This is a simplified version
    await this.page.keyboard.press('Tab');
    await this.page.keyboard.type(JSON.stringify(config, null, 2));
  }

  async save() {
    await this.saveButton.click();
  }
}
