/* eslint-disable react-hooks/rules-of-hooks, no-empty-pattern */
import { test as base, expect } from '@playwright/test';
import type { WorkerInfo } from '@playwright/test';
import getPort from 'get-port';
import { startBackend, startFrontend } from './process/servers';
import { createApiClient } from '../api/client';
import { DevicesFactory } from '../api/factories/devices';

type ServiceManager = {
  frontendUrl: string;
  backendUrl: string;
  disposeServices(): Promise<void>;
};

type TestFixtures = {
  frontendUrl: string;
  devices: DevicesFactory;
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

  devices: async ({ _serviceManager }, use) => {
    const client = createApiClient({ baseUrl: _serviceManager.backendUrl });
    const factory = new DevicesFactory(client);
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
