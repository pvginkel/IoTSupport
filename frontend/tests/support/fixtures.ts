/* eslint-disable react-hooks/rules-of-hooks, no-empty-pattern */
import { test as base, expect } from '@playwright/test';
import type { WorkerInfo } from '@playwright/test';
import getPort from 'get-port';
import { startBackend, startFrontend } from './process/servers';
import { DevicesFactory } from '../api/factories/devices';
import { DeviceModelsFactory } from '../api/factories/device-models';
import { AuthFactory } from '../api/factories/auth';

type ServiceManager = {
  frontendUrl: string;
  backendUrl: string;
  disposeServices(): Promise<void>;
};

type TestFixtures = {
  frontendUrl: string;
  devices: DevicesFactory;
  deviceModels: DeviceModelsFactory;
  auth: AuthFactory;
};

type InternalFixtures = {
  _serviceManager: ServiceManager;
};

export const test = base.extend<TestFixtures, InternalFixtures>({
  frontendUrl: async ({ _serviceManager }, use) => {
    await use(_serviceManager.frontendUrl);
  },

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

      const previousFrontend = process.env.FRONTEND_URL;

      const backendPort = await getPort();
      const frontendPort = await getPort({ exclude: [backendPort] });

      let backend: Awaited<ReturnType<typeof startBackend>> | undefined;
      let frontend: Awaited<ReturnType<typeof startFrontend>> | undefined;

      try {
        // Start backend first
        backend = await startBackend(workerInfo.workerIndex, {
          streamLogs: backendStreamLogs,
          port: backendPort,
        });

        // Start frontend with backend URL for the Vite proxy
        frontend = await startFrontend({
          workerIndex: workerInfo.workerIndex,
          backendUrl: backend.url,
          excludePorts: [backend.port],
          port: frontendPort,
          streamLogs: frontendStreamLogs,
        });
      } catch (error) {
        // Clean up if startup failed
        if (frontend) {
          await frontend.dispose();
        }
        if (backend) {
          await backend.dispose();
        }
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
      };

      const serviceManager: ServiceManager = {
        frontendUrl: frontend.url,
        backendUrl: backend.url,
        disposeServices,
      };

      try {
        await use(serviceManager);
      } finally {
        await disposeServices();
        process.env.FRONTEND_URL = previousFrontend;
      }
    },
    { scope: 'worker', timeout: 120_000 },
  ],
});

export { expect };
