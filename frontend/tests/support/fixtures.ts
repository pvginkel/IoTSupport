/* eslint-disable react-hooks/rules-of-hooks, no-empty-pattern */
import { test as base, expect } from '@playwright/test';
import type { WorkerInfo } from '@playwright/test';
import { copyFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import getPort from 'get-port';
import { startBackend, startFrontend } from './process/servers';
import {
  createBackendLogCollector,
  createFrontendLogCollector,
  type BackendLogCollector,
  type FrontendLogCollector,
} from './process/backend-logs';
import { DevicesFactory } from '../api/factories/devices';
import { DeviceModelsFactory } from '../api/factories/device-models';
import { AuthFactory } from '../api/factories/auth';

type ServiceManager = {
  frontendUrl: string;
  backendUrl: string;
  backendLogs: BackendLogCollector;
  frontendLogs: FrontendLogCollector;
  disposeServices(): Promise<void>;
};

type TestFixtures = {
  frontendUrl: string;
  backendLogs: BackendLogCollector;
  frontendLogs: FrontendLogCollector;
  devices: DevicesFactory;
  deviceModels: DeviceModelsFactory;
  auth: AuthFactory;
};

type InternalFixtures = {
  _serviceManager: ServiceManager;
};

/**
 * Call the Keycloak cleanup endpoint to delete Playwright test device clients.
 * Uses a pattern to match only clients created by Playwright tests (iotdevice-playwright_*).
 * This is called before each worker starts to ensure clean state.
 * Has a 30s timeout to prevent hanging during teardown.
 */
async function cleanupKeycloakClients(backendUrl: string): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30_000);

  try {
    const response = await fetch(`${backendUrl}/api/testing/keycloak-cleanup`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        pattern: 'iotdevice-playwright_.*',
      }),
      signal: controller.signal,
    });
    if (response.ok) {
      const data = await response.json();
      if (data.deleted_count > 0) {
        console.log(`[keycloak] Cleaned up ${data.deleted_count} device clients`);
      }
    }
  } catch {
    // Keycloak may not be configured in test environment, or request timed out - ignore errors
  } finally {
    clearTimeout(timeoutId);
  }
}

export const test = base.extend<TestFixtures, InternalFixtures>({
  frontendUrl: async ({ _serviceManager }, use) => {
    await use(_serviceManager.frontendUrl);
  },

  backendLogs: [
    async ({ _serviceManager }, use, testInfo) => {
      const attachment = await _serviceManager.backendLogs.attachToTest(testInfo);
      try {
        await use(_serviceManager.backendLogs);
      } finally {
        await attachment.stop();
      }
    },
    { auto: true },
  ],

  frontendLogs: [
    async ({ _serviceManager }, use, testInfo) => {
      const attachment = await _serviceManager.frontendLogs.attachToTest(testInfo);
      try {
        await use(_serviceManager.frontendLogs);
      } finally {
        await attachment.stop();
      }
    },
    { auto: true },
  ],

  baseURL: async ({ frontendUrl }, use) => {
    await use(frontendUrl);
  },

  devices: async ({ _serviceManager, page, auth }, use) => {
    // Authenticate first - backend requires auth for all API calls
    // Device operations require admin role
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    // Use frontend URL and page.request to share cookies with browser
    const factory = new DevicesFactory(_serviceManager.frontendUrl, page);
    await use(factory);
  },

  deviceModels: async ({ _serviceManager, page, auth }, use) => {
    // Authenticate first - backend requires auth for all API calls
    // Device model operations require admin role
    await auth.createSession({ name: 'Test User', roles: ['admin'] });

    // Use frontend URL and page.request to share cookies with browser
    const factory = new DeviceModelsFactory(_serviceManager.frontendUrl, page);
    await use(factory);
  },

  auth: async ({ _serviceManager, page }, use) => {
    // Use frontend URL so cookies are set on the correct origin
    // The /api/* routes are proxied to the backend
    // Uses page.request to share cookies with the browser context
    const factory = new AuthFactory(_serviceManager.frontendUrl, page);
    await use(factory);
  },

  page: async ({ page }, use) => {
    // Suppress expected console errors that don't indicate test failures
    const expectedErrors: RegExp[] = [
      /Unable to preventDefault inside passive event listener invocation\./,
    ];

    await page.exposeFunction('__registerExpectedError', (pattern: string, flags?: string) => {
      expectedErrors.push(new RegExp(pattern, flags));
    });

    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();

        if (expectedErrors.some(pattern => pattern.test(text))) {
          return;
        }

        // Allow backend validation errors (409/conflict, 400/validation)
        if (
          text.includes('409') ||
          text.includes('CONFLICT') ||
          text.includes('already exists') ||
          text.includes('duplicate') ||
          text.includes('400') ||
          text.includes('validation')
        ) {
          return;
        }

        // Allow 404 errors for recently deleted resources
        if (text.includes('404') || text.includes('NOT FOUND')) {
          return;
        }

        // Allow 401 errors during auth tests (expected when unauthenticated)
        if (text.includes('401') || text.includes('UNAUTHORIZED')) {
          return;
        }

        // Allow 403 errors during auth tests (expected for forbidden resources)
        if (text.includes('403') || text.includes('FORBIDDEN')) {
          return;
        }

        // Allow 500 errors during auth error tests
        if (text.includes('500') || text.includes('INTERNAL SERVER ERROR')) {
          return;
        }

        // Allow 503 errors (service unavailable - expected in test env where ES may not be running)
        if (text.includes('503') || text.includes('SERVICE UNAVAILABLE')) {
          return;
        }

        throw new Error(`Console error: ${text}`);
      }
    });

    page.on('pageerror', err => {
      throw err;
    });

    // Disable animations for deterministic tests
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addStyleTag({
      content: `*, *::before, *::after {
        transition-duration: 0s !important;
        animation-duration: 0s !important;
        animation-delay: 0s !important;
      }`,
    });

    try {
      await use(page);
    } finally {
      expectedErrors.length = 0;
    }
  },

  _serviceManager: [
    async ({}, use: (value: ServiceManager) => Promise<void>, workerInfo: WorkerInfo) => {
      const backendStreamLogs = process.env.PLAYWRIGHT_BACKEND_LOG_STREAM === 'true';
      const frontendStreamLogs = process.env.PLAYWRIGHT_FRONTEND_LOG_STREAM === 'true';

      // Create log collectors
      const backendLogs = createBackendLogCollector({
        workerIndex: workerInfo.workerIndex,
        streamToConsole: backendStreamLogs,
      });
      const frontendLogs = createFrontendLogCollector({
        workerIndex: workerInfo.workerIndex,
        streamToConsole: frontendStreamLogs,
      });

      const previousFrontend = process.env.FRONTEND_URL;

      // Get seeded database path from global setup
      const seedDbPath = process.env.PLAYWRIGHT_SEEDED_SQLITE_DB;
      if (!seedDbPath) {
        backendLogs.dispose();
        frontendLogs.dispose();
        throw new Error(
          'PLAYWRIGHT_SEEDED_SQLITE_DB is not set. Ensure global setup initialized the test database.'
        );
      }

      // Create per-worker database copy
      let workerDbDir: string | undefined;
      let workerDbPath: string | undefined;

      const cleanupWorkerDb = async () => {
        if (workerDbDir) {
          try {
            await rm(workerDbDir, { recursive: true, force: true });
          } catch {
            // Ignore cleanup errors
          }
        }
      };

      try {
        workerDbDir = await mkdtemp(
          join(tmpdir(), `iotsupport-worker-${workerInfo.workerIndex}-`)
        );
        workerDbPath = join(workerDbDir, 'database.sqlite');
        await copyFile(seedDbPath, workerDbPath);
        backendLogs.log(`Using SQLite database copy at ${workerDbPath}`);
      } catch (error) {
        backendLogs.dispose();
        frontendLogs.dispose();
        await cleanupWorkerDb();
        throw error;
      }

      const backendPort = await getPort();
      const frontendPort = await getPort({ exclude: [backendPort] });

      let backend: Awaited<ReturnType<typeof startBackend>> | undefined;
      let frontend: Awaited<ReturnType<typeof startFrontend>> | undefined;

      try {
        // Start backend first with SQLite database
        backend = await startBackend(workerInfo.workerIndex, {
          streamLogs: backendStreamLogs,
          port: backendPort,
          sqliteDbPath: workerDbPath,
        });

        // Attach backend process streams to log collector
        backendLogs.attachStream(backend.process.stdout, 'stdout');
        backendLogs.attachStream(backend.process.stderr, 'stderr');
        backendLogs.log(`Backend listening on ${backend.url}`);

        // Clean up any leftover Keycloak clients from previous test runs
        await cleanupKeycloakClients(backend.url);

        // Start frontend with backend URL for the Vite proxy
        frontend = await startFrontend({
          workerIndex: workerInfo.workerIndex,
          backendUrl: backend.url,
          excludePorts: [backend.port],
          port: frontendPort,
          streamLogs: frontendStreamLogs,
        });

        // Attach frontend process streams to log collector
        frontendLogs.attachStream(frontend.process.stdout, 'stdout');
        frontendLogs.attachStream(frontend.process.stderr, 'stderr');
        frontendLogs.log(`Frontend listening on ${frontend.url}`);
      } catch (error) {
        // Clean up if startup failed
        if (frontend) {
          await frontend.dispose();
        }
        if (backend) {
          await backend.dispose();
        }
        backendLogs.dispose();
        frontendLogs.dispose();
        await cleanupWorkerDb();
        throw error;
      }

      process.env.FRONTEND_URL = frontend.url;

      if (workerInfo.project?.use) {
        const projectUse = workerInfo.project.use as { baseURL?: string };
        projectUse.baseURL = frontend.url;
      }

      let disposed = false;
      const disposeServices = async () => {
        if (disposed) {
          return;
        }
        disposed = true;

        // Clean up Keycloak clients before disposing services
        if (backend) {
          await cleanupKeycloakClients(backend.url);
        }

        // Dispose in reverse order: frontend -> backend
        if (frontend) {
          try {
            await frontend.dispose();
          } catch (error) {
            console.warn(
              `[worker-${workerInfo.workerIndex}] Failed to dispose frontend:`,
              error
            );
          }
        }
        if (backend) {
          try {
            await backend.dispose();
          } catch (error) {
            console.warn(
              `[worker-${workerInfo.workerIndex}] Failed to dispose backend:`,
              error
            );
          }
        }

        // Clean up worker database
        await cleanupWorkerDb();
      };

      const serviceManager: ServiceManager = {
        frontendUrl: frontend.url,
        backendUrl: backend.url,
        backendLogs,
        frontendLogs,
        disposeServices,
      };

      try {
        await use(serviceManager);
      } finally {
        await disposeServices();
        process.env.FRONTEND_URL = previousFrontend;
        backendLogs.dispose();
        frontendLogs.dispose();
      }
    },
    { scope: 'worker', timeout: 120_000 },
  ],
});

export { expect };
