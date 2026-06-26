import type { Page, Locator } from '@playwright/test';

/**
 * Page object for the rotation dashboard.
 * Provides locators and actions for SSE nudge specs.
 */
export class RotationPage {
  constructor(private page: Page) {}

  // Navigation
  async goto() {
    await this.page.goto('/rotation');
  }

  // Locators
  get dashboard(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard"]');
  }

  get errorState(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.error"]');
  }

  get loadingState(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.loading"]');
  }

  get panels(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.panels"]');
  }

  get rows(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.row"]');
  }

  get triggerButton(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.trigger-button"]');
  }

  get healthyPanel(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.panel.healthy"]');
  }

  get warningPanel(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.panel.warning"]');
  }

  get criticalPanel(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.panel.critical"]');
  }

  get confirmDialog(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.confirm-dialog"]');
  }

  get noPendingIndicator(): Locator {
    return this.page.locator('[data-testid="rotation.dashboard.no-pending"]');
  }

  // Row locators
  rowByDeviceId(deviceId: number): Locator {
    return this.page.locator(`[data-testid="rotation.dashboard.row"][data-device-id="${deviceId}"]`);
  }

  getRowRotationState(deviceId: number): Locator {
    return this.rowByDeviceId(deviceId);
  }

  // Actions
  async waitForDashboardLoaded() {
    await this.dashboard.waitFor({ state: 'visible', timeout: 15_000 });
    await this.panels.waitFor({ state: 'visible', timeout: 15_000 });
  }

  async triggerFleetRotation() {
    await this.triggerButton.click();
  }

  async confirmTrigger() {
    await this.confirmDialog.locator('button:has-text("Trigger Rotation")').click();
  }
}
