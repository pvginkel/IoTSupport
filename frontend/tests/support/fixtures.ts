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
 * The model-code prefix this worker uses. Workers run fully parallel against one
 * shared Keycloak realm, so the prefix carries the worker index: it is what lets
 * teardown delete only the clients this worker created and leave another worker's
 * in-flight device clients alone. Must stay [a-z0-9_]+ (the model code is validated
 * by backend/app/utils/device_auth.py), and randomModelCode's trailing underscore
 * keeps the w1 prefix from matching w10's clients.
 */
function workerCodePrefix(workerIndex: number): string {
  return `playwright_w${workerIndex}`;
}

/**
 * Call the Keycloak cleanup endpoint to delete this worker's test device clients.
 * A device's client id is `iotdevice-<model code>-<key>`, so anchoring the pattern
 * on the worker's own code prefix (iotdevice-playwright_w<N>_*) scopes the delete to
 * the calling worker. The backend matches with re.match, so the pattern is anchored.
 * Has a 30s timeout to prevent hanging during teardown.
 */
async function cleanupKeycloakClients(baseUrl: string, codePrefix: string): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);

  try {
    const response = await fetch(`${baseUrl}/api/testing/keycloak-cleanup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pattern: `^iotdevice-${codePrefix}_` }),
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
  devices: async ({ frontendUrl, page, auth }, use, testInfo) => {
    await auth.createSession({ name: 'Test User', roles: ['editor'] });
    const codePrefix = workerCodePrefix(testInfo.workerIndex);
    const factory = new DevicesFactory(frontendUrl, page, codePrefix);
    try {
      await use(factory);
    } finally {
      await cleanupKeycloakClients(frontendUrl, codePrefix);
    }
  },

  // Same prefix as `devices`: a spec that creates its model here and its device
  // there must still produce a client that this worker's cleanup matches.
  deviceModels: async ({ frontendUrl, page, auth }, use, testInfo) => {
    await auth.createSession({ name: 'Test User', roles: ['editor'] });
    const factory = new DeviceModelsFactory(
      frontendUrl,
      page,
      workerCodePrefix(testInfo.workerIndex)
    );
    await use(factory);
  },
});

export { expect } from '@playwright/test';
