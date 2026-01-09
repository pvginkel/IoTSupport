# Playwright Implementation Plan

This document details the Playwright test infrastructure setup for the IoT Support frontend. The architecture mirrors the proven setup from ElectronicsInventory, adapted for IoT Support's simpler data model (JSON files instead of SQLite).

## Architecture Overview

### Per-Worker Service Isolation

Each Playwright worker runs completely isolated services:

```
┌─────────────────────────────────────────────────────────────┐
│                    Playwright Worker N                       │
├─────────────────────────────────────────────────────────────┤
│  Backend Service                                             │
│  - Port: dynamically allocated                               │
│  - Config dir: /tmp/iot-support-worker-N-{random}/configs   │
│  - Health: GET /api/health                                   │
├─────────────────────────────────────────────────────────────┤
│  Frontend Service                                            │
│  - Port: dynamically allocated                               │
│  - BACKEND_URL: points to worker's backend                   │
│  - VITE_TEST_MODE: true                                      │
│  - Vite cache: isolated per worker                           │
├─────────────────────────────────────────────────────────────┤
│  Test Data                                                   │
│  - API factories create configs via backend API              │
│  - Each test seeds its own data                              │
│  - No cleanup needed (temp dir destroyed after worker)       │
└─────────────────────────────────────────────────────────────┘
```

### Key Differences from ElectronicsInventory

| Aspect | ElectronicsInventory | IoT Support |
|--------|---------------------|-------------|
| Database | SQLite (copied per worker) | JSON files (temp dir per worker) |
| SSE Gateway | Yes | No (out of scope) |
| Data seeding | Global setup seeds DB, workers copy | Workers create empty config dir |
| Complexity | 3 services per worker | 2 services per worker |

## Implementation Phases

### Phase 1: Configuration Files

#### 1.1 Playwright Configuration (`playwright.config.ts`)

```typescript
import { defineConfig, devices } from '@playwright/test';
import path from 'path';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 1 : 2,
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],

  globalSetup: './tests/support/global-setup.ts',

  use: {
    baseURL: 'http://localhost:3200',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },

  expect: {
    timeout: 10_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
```

#### 1.2 Environment File (`.env.test`)

```bash
# Playwright test configuration
PLAYWRIGHT_MANAGED_SERVICES=true

# Log streaming (enable for debugging)
# PLAYWRIGHT_BACKEND_LOG_STREAM=true
# PLAYWRIGHT_FRONTEND_LOG_STREAM=true
```

### Phase 2: Global Setup

#### 2.1 Global Setup (`tests/support/global-setup.ts`)

```typescript
import { FullConfig } from '@playwright/test';
import dotenv from 'dotenv';
import path from 'path';

export default async function globalSetup(config: FullConfig): Promise<void> {
  // Load test environment
  dotenv.config({ path: path.resolve(__dirname, '../../.env.test') });

  // Validate managed services mode
  if (process.env.PLAYWRIGHT_MANAGED_SERVICES === 'false') {
    throw new Error(
      'External services mode has been removed. ' +
      'All tests use per-worker managed services.'
    );
  }

  console.log('[global-setup] IoT Support test environment initialized');
}
```

### Phase 3: Test Fixtures

#### 3.1 Service Manager (`tests/support/fixtures.ts`)

The fixtures file provides:

1. **`_serviceManager`** (worker-scoped): Starts backend and frontend per worker
2. **`backendUrl`**: URL to worker's backend
3. **`frontendUrl`**: URL to worker's frontend
4. **`apiClient`**: OpenAPI client configured for worker's backend
5. **`testData`**: Factory bundle for creating test configs
6. **`page`**: Enhanced page with test event bridge and error handling
7. **`testEvents`**: Test event capture buffer
8. **`devices`**: Page object for device config interactions

Key implementation details:

```typescript
type ServiceManager = {
  backendUrl: string;
  frontendUrl: string;
  configDir: string;
  backendLogs: LogCollector;
  frontendLogs: LogCollector;
  disposeServices(): Promise<void>;
};

// Worker fixture starts services sequentially:
// 1. Create temp config directory
// 2. Start backend with ESP32_CONFIGS_DIR pointing to temp dir
// 3. Wait for backend health check (GET /api/health returns 200)
// 4. Start frontend with BACKEND_URL pointing to worker's backend
// 5. Wait for frontend to respond (GET / returns 200)
```

#### 3.2 Port Allocation

Use `get-port` package to allocate unique ports per worker:

```typescript
import getPort from 'get-port';

const backendPort = await getPort({ exclude: usedPorts });
const frontendPort = await getPort({ exclude: [...usedPorts, backendPort] });
```

#### 3.3 Log Collection

Attach service logs to test results on failure:

```typescript
class LogCollector {
  private lines: string[] = [];
  private stream: boolean;

  constructor(serviceName: string, workerIndex: number) {
    this.stream = process.env[`PLAYWRIGHT_${serviceName.toUpperCase()}_LOG_STREAM`] === 'true';
  }

  append(line: string, isStderr: boolean): void {
    this.lines.push(line);
    if (this.stream) {
      console.log(`[worker-${this.workerIndex} ${this.serviceName}] ${line}`);
    }
  }

  getContents(): string {
    return this.lines.join('\n');
  }
}
```

### Phase 4: Service Scripts

#### 4.1 Backend Testing Server

The backend already has `scripts/testing-server.sh`. Verify it:
- Accepts `--host`, `--port` arguments
- Respects `ESP32_CONFIGS_DIR` environment variable
- Sets `FLASK_ENV=testing`

#### 4.2 Frontend Testing Server (`scripts/testing-server.sh`)

Create new script:

```bash
#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(dirname "$SCRIPT_DIR")"

cd "$FRONTEND_DIR"

HOST="127.0.0.1"
PORT="3200"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

export VITE_TEST_MODE=true
export NODE_ENV=test

# Use isolated Vite cache if specified
if [[ -n "${VITE_CACHE_DIR:-}" ]]; then
  export VITE_CACHE_DIR
fi

exec pnpm exec vite --host "$HOST" --port "$PORT" --strictPort --mode test
```

### Phase 5: Process Management

#### 5.1 Server Startup (`tests/support/process/servers.ts`)

```typescript
export async function startBackendService(options: {
  host: string;
  port: number;
  configDir: string;
  logCollector: LogCollector;
}): Promise<ChildProcess> {
  const backendDir = path.resolve(__dirname, '../../../../backend');
  const proc = spawn(
    path.join(backendDir, 'scripts/testing-server.sh'),
    ['--host', options.host, '--port', String(options.port)],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        ESP32_CONFIGS_DIR: options.configDir,
        FLASK_ENV: 'testing',
      },
    }
  );

  // Attach log collector to stdout/stderr
  // Wait for health check: GET /api/health returns 200
  await waitForEndpoint(`http://${options.host}:${options.port}/api/health`, 30_000);

  return proc;
}

export async function startFrontendService(options: {
  host: string;
  port: number;
  backendUrl: string;
  logCollector: LogCollector;
}): Promise<ChildProcess> {
  const frontendDir = path.resolve(__dirname, '../../../');
  const proc = spawn(
    path.join(frontendDir, 'scripts/testing-server.sh'),
    ['--host', options.host, '--port', String(options.port)],
    {
      cwd: frontendDir,
      env: {
        ...process.env,
        BACKEND_URL: options.backendUrl,
        VITE_TEST_MODE: 'true',
        NODE_ENV: 'test',
      },
    }
  );

  // Wait for frontend to respond
  await waitForEndpoint(`http://${options.host}:${options.port}/`, 90_000);

  return proc;
}
```

#### 5.2 Health Check Polling

```typescript
async function waitForEndpoint(url: string, timeoutMs: number): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // Service not ready yet
    }
    await sleep(200);
  }
  throw new Error(`Timeout waiting for ${url}`);
}
```

### Phase 6: Test Event System

#### 6.1 Test Event Types (`src/types/test-events.ts`)

```typescript
export const TestEventKind = {
  ROUTE: 'route',
  FORM: 'form',
  API: 'api',
  TOAST: 'toast',
  ERROR: 'error',
  QUERY_ERROR: 'query_error',
  UI_STATE: 'ui_state',
  LIST_LOADING: 'list_loading',
} as const;

export type TestEventKind = (typeof TestEventKind)[keyof typeof TestEventKind];

export interface TestEventPayload {
  kind: TestEventKind;
  timestamp: number;
  [key: string]: unknown;
}

// Specific event payloads
export interface ListLoadingEvent extends TestEventPayload {
  kind: 'list_loading';
  phase: 'loading' | 'ready' | 'error';
  listId: string;
  itemCount?: number;
}

export interface FormEvent extends TestEventPayload {
  kind: 'form';
  action: 'open' | 'submit' | 'success' | 'error' | 'validation_error';
  formId: string;
  error?: string;
}
```

#### 6.2 Test Mode Guard (`src/lib/config/test-mode.ts`)

```typescript
export function isTestMode(): boolean {
  return import.meta.env.VITE_TEST_MODE === 'true';
}

export const TEST_MODE = isTestMode();
```

#### 6.3 Event Emitter (`src/lib/test/event-emitter.ts`)

```typescript
import { isTestMode } from '../config/test-mode';
import type { TestEventPayload } from '../../types/test-events';

declare global {
  interface Window {
    __playwright_emitTestEvent?: (payload: TestEventPayload) => void;
  }
}

export function emitTestEvent(payload: Omit<TestEventPayload, 'timestamp'>): void {
  if (!isTestMode()) return;

  const fullPayload: TestEventPayload = {
    ...payload,
    timestamp: Date.now(),
  };

  window.__playwright_emitTestEvent?.(fullPayload);
}
```

#### 6.4 Test Event Bridge (`tests/support/helpers/test-events.ts`)

```typescript
import { Page } from '@playwright/test';
import type { TestEventPayload, TestEventKind } from '../../../src/types/test-events';

export class TestEventCapture {
  private events: TestEventPayload[] = [];
  private readonly maxEvents = 500;

  constructor(private page: Page) {}

  async setup(): Promise<void> {
    await this.page.exposeFunction('__playwright_emitTestEvent', (payload: TestEventPayload) => {
      if (this.events.length >= this.maxEvents) {
        throw new Error('Test event buffer overflow');
      }
      this.events.push(payload);
    });
  }

  getEvents(): TestEventPayload[] {
    return [...this.events];
  }

  async waitForEvent(
    kind: TestEventKind,
    filter?: (event: TestEventPayload) => boolean,
    timeout = 10_000
  ): Promise<TestEventPayload> {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const match = this.events.find(e =>
        e.kind === kind && (!filter || filter(e))
      );
      if (match) return match;
      await this.page.waitForTimeout(100);
    }
    throw new Error(`Timeout waiting for ${kind} event`);
  }

  clear(): void {
    this.events = [];
  }
}
```

### Phase 7: API Client & Factories

#### 7.1 API Client (`tests/api/client.ts`)

```typescript
import createClient from 'openapi-fetch';
import type { paths } from '../../src/lib/api/generated/types';

export function createApiClient(options?: { baseUrl?: string }) {
  return createClient<paths>({
    baseUrl: options?.baseUrl ?? 'http://localhost:3201',
  });
}

export type ApiClient = ReturnType<typeof createApiClient>;
```

#### 7.2 Config Factory (`tests/api/factories/config-factory.ts`)

```typescript
import type { ApiClient } from '../client';

export interface ConfigFactoryOptions {
  client: ApiClient;
}

export class ConfigTestFactory {
  constructor(private client: ApiClient) {}

  randomMacAddress(): string {
    const hex = () => Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
    return `${hex()}-${hex()}-${hex()}-${hex()}-${hex()}-${hex()}`;
  }

  async create(options?: {
    macAddress?: string;
    content?: Record<string, unknown>;
  }): Promise<{ macAddress: string; content: Record<string, unknown> }> {
    const macAddress = options?.macAddress ?? this.randomMacAddress();
    const content = options?.content ?? {
      deviceName: `Test Device ${macAddress.slice(0, 8)}`,
      deviceEntityId: `test_device_${Date.now()}`,
      enableOTA: false,
    };

    const response = await this.client.PUT('/api/configs/{mac_address}', {
      params: { path: { mac_address: macAddress } },
      body: { content },
    });

    if (response.error) {
      throw new Error(`Failed to create config: ${JSON.stringify(response.error)}`);
    }

    return { macAddress, content };
  }

  async createMany(count: number): Promise<Array<{ macAddress: string; content: Record<string, unknown> }>> {
    return Promise.all(Array.from({ length: count }, () => this.create()));
  }

  async delete(macAddress: string): Promise<void> {
    await this.client.DELETE('/api/configs/{mac_address}', {
      params: { path: { mac_address: macAddress } },
    });
  }
}
```

#### 7.3 Test Data Bundle (`tests/api/index.ts`)

```typescript
import { createApiClient, type ApiClient } from './client';
import { ConfigTestFactory } from './factories/config-factory';

export { createApiClient, type ApiClient };

export function createTestDataBundle(
  client: ApiClient,
  options?: { backendUrl?: string }
) {
  return {
    configs: new ConfigTestFactory(client),
  };
}

export type TestDataBundle = ReturnType<typeof createTestDataBundle>;
```

### Phase 8: Page Objects

#### 8.1 Base Page (`tests/support/page-objects/base-page.ts`)

```typescript
import { Page, Locator } from '@playwright/test';

export abstract class BasePage {
  constructor(protected page: Page) {}

  async goto(path: string): Promise<void> {
    await this.page.goto(path);
  }

  getByTestId(id: string): Locator {
    return this.page.getByTestId(id);
  }
}
```

#### 8.2 Devices Page (`tests/support/page-objects/devices-page.ts`)

```typescript
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base-page';

export class DevicesPage extends BasePage {
  readonly list: Locator;
  readonly newDeviceButton: Locator;
  readonly emptyState: Locator;

  constructor(page: Page) {
    super(page);
    this.list = page.getByTestId('device-list');
    this.newDeviceButton = page.getByTestId('new-device-button');
    this.emptyState = page.getByTestId('device-list-empty');
  }

  async gotoList(): Promise<void> {
    await this.goto('/devices');
  }

  async waitForListLoaded(): Promise<void> {
    // Wait for list loading instrumentation event
    await expect(this.list.or(this.emptyState)).toBeVisible();
  }

  async getDeviceRow(macAddress: string): Locator {
    return this.page.getByTestId(`device-row-${macAddress}`);
  }

  async openNewDevice(): Promise<void> {
    await this.newDeviceButton.click();
    await expect(this.page).toHaveURL(/\/devices\/new/);
  }

  async openEditDevice(macAddress: string): Promise<void> {
    const row = await this.getDeviceRow(macAddress);
    await row.getByTestId('edit-button').click();
  }

  async deleteDevice(macAddress: string): Promise<void> {
    const row = await this.getDeviceRow(macAddress);
    await row.getByTestId('delete-button').click();
    // Confirm in dialog
    await this.page.getByTestId('confirm-delete-button').click();
  }
}
```

#### 8.3 Device Editor Page (`tests/support/page-objects/device-editor-page.ts`)

```typescript
import { Page, Locator, expect } from '@playwright/test';
import { BasePage } from './base-page';

export class DeviceEditorPage extends BasePage {
  readonly macAddressInput: Locator;
  readonly editor: Locator;
  readonly saveButton: Locator;
  readonly cancelButton: Locator;
  readonly duplicateButton: Locator;

  constructor(page: Page) {
    super(page);
    this.macAddressInput = page.getByTestId('mac-address-input');
    this.editor = page.getByTestId('json-editor');
    this.saveButton = page.getByTestId('save-button');
    this.cancelButton = page.getByTestId('cancel-button');
    this.duplicateButton = page.getByTestId('duplicate-button');
  }

  async setMacAddress(mac: string): Promise<void> {
    await this.macAddressInput.clear();
    await this.macAddressInput.fill(mac);
  }

  async setContent(json: Record<string, unknown>): Promise<void> {
    // Monaco editor interaction
    await this.editor.click();
    await this.page.keyboard.press('ControlOrMeta+a');
    await this.page.keyboard.type(JSON.stringify(json, null, 2));
  }

  async save(): Promise<void> {
    await this.saveButton.click();
  }

  async cancel(): Promise<void> {
    await this.cancelButton.click();
  }

  async duplicate(): Promise<void> {
    await this.duplicateButton.click();
  }

  async expectMacAddress(mac: string): Promise<void> {
    await expect(this.macAddressInput).toHaveValue(mac);
  }
}
```

### Phase 9: Instrumentation Hooks

#### 9.1 List Loading Instrumentation (`src/lib/test/useListLoadingInstrumentation.ts`)

```typescript
import { useEffect } from 'react';
import { emitTestEvent } from './event-emitter';
import { isTestMode } from '../config/test-mode';

export function useListLoadingInstrumentation(
  listId: string,
  isLoading: boolean,
  isError: boolean,
  itemCount?: number
): void {
  useEffect(() => {
    if (!isTestMode()) return;

    if (isLoading) {
      emitTestEvent({ kind: 'list_loading', phase: 'loading', listId });
    } else if (isError) {
      emitTestEvent({ kind: 'list_loading', phase: 'error', listId });
    } else {
      emitTestEvent({ kind: 'list_loading', phase: 'ready', listId, itemCount });
    }
  }, [listId, isLoading, isError, itemCount]);
}
```

#### 9.2 Form Instrumentation (`src/lib/test/useFormInstrumentation.ts`)

```typescript
import { emitTestEvent } from './event-emitter';
import { isTestMode } from '../config/test-mode';

export function trackFormSubmit(formId: string): void {
  if (!isTestMode()) return;
  emitTestEvent({ kind: 'form', action: 'submit', formId });
}

export function trackFormSuccess(formId: string): void {
  if (!isTestMode()) return;
  emitTestEvent({ kind: 'form', action: 'success', formId });
}

export function trackFormError(formId: string, error: string): void {
  if (!isTestMode()) return;
  emitTestEvent({ kind: 'form', action: 'error', formId, error });
}
```

### Phase 10: Smoke Tests

#### 10.1 Basic Smoke Test (`tests/smoke.spec.ts`)

```typescript
import { test, expect } from './support/fixtures';

test.describe('Smoke Tests', () => {
  test('frontend loads and displays app shell', async ({ page, frontendUrl }) => {
    await page.goto(frontendUrl);
    await expect(page).toHaveTitle(/IoT Support/);
    await expect(page.getByTestId('sidebar')).toBeVisible();
  });

  test('backend health endpoint responds', async ({ backendUrl }) => {
    const response = await fetch(`${backendUrl}/api/health`);
    expect(response.status).toBe(200);
  });

  test('device list loads (empty state)', async ({ devices }) => {
    await devices.gotoList();
    await devices.waitForListLoaded();
    await expect(devices.emptyState).toBeVisible();
  });
});
```

## File Structure

```
tests/
├── api/
│   ├── client.ts                    # OpenAPI client wrapper
│   ├── index.ts                     # Test data bundle export
│   └── factories/
│       └── config-factory.ts        # Config CRUD factory
├── e2e/
│   └── devices/
│       ├── list.spec.ts             # Device list tests
│       ├── create.spec.ts           # Create device tests
│       ├── edit.spec.ts             # Edit device tests
│       └── delete.spec.ts           # Delete device tests
├── support/
│   ├── fixtures.ts                  # Custom Playwright fixtures
│   ├── global-setup.ts              # Global test setup
│   ├── helpers/
│   │   ├── test-events.ts           # Test event bridge
│   │   └── index.ts                 # Helper exports
│   ├── page-objects/
│   │   ├── base-page.ts             # Base page object
│   │   ├── devices-page.ts          # Device list page object
│   │   └── device-editor-page.ts    # Device editor page object
│   └── process/
│       ├── servers.ts               # Service startup/shutdown
│       └── log-collector.ts         # Log collection
└── smoke.spec.ts                    # Basic smoke tests

src/
├── lib/
│   ├── config/
│   │   └── test-mode.ts             # Test mode detection
│   └── test/
│       ├── event-emitter.ts         # Test event emission
│       ├── useListLoadingInstrumentation.ts
│       └── useFormInstrumentation.ts
└── types/
    └── test-events.ts               # Test event type definitions

scripts/
└── testing-server.sh                # Frontend test server script
```

## Dependencies

Add to `package.json`:

```json
{
  "devDependencies": {
    "@playwright/test": "^1.40.0",
    "dotenv": "^16.3.1",
    "get-port": "^7.0.0",
    "split2": "^4.2.0"
  }
}
```

## Verification Checklist

Before considering Playwright setup complete:

- [ ] `pnpm playwright test tests/smoke.spec.ts` passes
- [ ] Services start and stop cleanly per worker
- [ ] Logs attached to test results on failure
- [ ] Test events emitted and captured correctly
- [ ] API factories can create/delete configs
- [ ] Page objects navigate and interact correctly
- [ ] No port conflicts with multiple workers
- [ ] `PLAYWRIGHT_BACKEND_LOG_STREAM=true` shows logs in real-time

## References

- [Testing Overview](./contribute/testing/index.md)
- [Factories & Fixtures](./contribute/testing/factories_and_fixtures.md)
- [CI & Execution](./contribute/testing/ci_and_execution.md)
- [Page Objects](./contribute/testing/page_objects.md)
- [No-Sleep Patterns](./contribute/testing/no_sleep_patterns.md)
