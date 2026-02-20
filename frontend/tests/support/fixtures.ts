/**
 * Domain-specific test fixtures.
 * App-owned — extends infrastructure fixtures with domain page objects and factories.
 *
 * Service management (backend, SSE gateway, frontend startup) is handled by
 * fixtures-infrastructure.ts. This file only adds app-specific fixtures.
 */

/* eslint-disable react-hooks/rules-of-hooks */
import { infrastructureFixtures } from './fixtures-infrastructure';
import { DevicesFactory } from '../api/factories/devices';
import { DeviceModelsFactory } from '../api/factories/device-models';

type AppFixtures = {
  devices: DevicesFactory;
  deviceModels: DeviceModelsFactory;
};

/**
 * Call the Keycloak cleanup endpoint to delete Playwright test device clients.
 * Uses a pattern to match only clients created by Playwright tests (iotdevice-playwright_*).
 * Has a 30s timeout to prevent hanging during teardown.
 */
async function cleanupKeycloakClients(baseUrl: string): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);

  try {
    const response = await fetch(`${baseUrl}/api/testing/keycloak-cleanup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pattern: 'iotdevice-playwright_.*' }),
      signal: controller.signal,
    });
    if (response.ok) {
      const data = await response.json();
      if (data.deleted_count > 0) {
        console.log(`[keycloak] Cleaned up ${data.deleted_count} device clients`);
      }
    }
  } catch {
    // Keycloak may not be configured in test environment, or request timed out
  } finally {
    clearTimeout(timeoutId);
  }
}

export const test = infrastructureFixtures.extend<AppFixtures>({
  devices: async ({ frontendUrl, page, auth }, use) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });
    const factory = new DevicesFactory(frontendUrl, page);
    try {
      await use(factory);
    } finally {
      await cleanupKeycloakClients(frontendUrl);
    }
  },

  deviceModels: async ({ frontendUrl, page, auth }, use) => {
    await auth.createSession({ name: 'Test User', roles: ['admin'] });
    const factory = new DeviceModelsFactory(frontendUrl, page);
    await use(factory);
  },
});

export { expect } from '@playwright/test';
