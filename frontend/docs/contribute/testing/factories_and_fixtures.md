# Factories & Fixtures

Factories and fixtures power the API-first testing strategy. They seed deterministic data through the
real backend, expose shared helpers, and keep specs concise — so every spec hits the real backend
without request interception. The `testing/no-route-mocks` ESLint rule bans `page.route`, its
`fulfill`/`abort` handlers and SSE mocks in every Playwright source.

The one stand-in the suite has is for what no test can reach: the USB serial port and the ESP32 chip
behind it, faked for Provision device and Flash device
([the fake USB device](#the-fake-usb-device)). Even there, every request still goes to the real
backend.

## API Client (`tests/api/client.ts`)

- `createApiClient({ baseUrl, fetch })` – an `openapi-fetch` client typed from the generated
  `src/lib/api/generated/types`.
- `createPlaywrightFetch(page.request)` – a `fetch` over the page's request context, so the client
  shares the browser's cookies and acts as the session `auth.createSession()` set.
- `apiRequest(() => client.POST(...))` – throws on a non-2xx answer, naming the backend's error, and
  retries 502, 503 and 504 up to three times.

## Factories (`tests/api/factories/`)

Each factory is a fixture. Before handing it out, the fixture creates an `editor` session and builds
the factory on the worker's frontend URL (the Vite proxy) with the worker's model-code prefix,
`playwright_w<N>`.

- **`DeviceModelsFactory` (`device-models.ts`)** — fixture `deviceModels`
  - `create({ code?, name?, configSchema? })` – POST `/api/device-models`
  - `seedFirmware(modelId, { version?, flashImages?, chip? })` – POST
    `/api/testing/device-models/{model_id}/firmware`, which stores the version through the real
    firmware upload and makes it the model's current one. Left out, the backend seeds a flashable
    `1.0.0-test` for the `esp32s3`; `flashImages: false` stores a version without flash images.
  - `get(id)`, `list()`, `findByCode(code)`, `delete(id)`
  - `randomModelCode(prefix?)`, `randomModelName(prefix?)`
- **`DevicesFactory` (`devices.ts`)** — fixture `devices`
  - `create({ deviceModelId?, deviceName?, deviceEntityId?, enableOta?, config? })` – POST
    `/api/devices`; creates a model first when `deviceModelId` is left out
  - `getFlashImages(deviceId)` – GET `/api/devices/{device_id}/flash-images`, what Flash device
    writes
  - `update({ id, active, config })`, `get(id)`, `list()`, `findIdByKey(key)`, `deleteByKey(key)`,
    `delete(id)`
  - `createCoredump({ deviceId, chip?, firmwareVersion?, size?, parseStatus?, parsedOutput? })` –
    POST `/api/testing/coredumps`
  - `randomDeviceName(prefix?)`, `randomDeviceEntityId(prefix?)`
  - `deviceModels` – the factory's own `DeviceModelsFactory`

A device's Keycloak client is `iotdevice-<model code>-<key>`. The `devices` fixture's teardown posts
`^iotdevice-playwright_w<N>_` to `/api/testing/keycloak-cleanup`, deleting this worker's clients and
leaving another worker's in-flight ones alone. Create models through the factory so their codes carry
the prefix the cleanup matches.

If a factory lacks behavior you need, add it and extend the backend as required — do **not** fill
the gap with Playwright `page.route` stubs. Land the factory method before the spec, so the spec
seeds state through the fixture rather than ad hoc API calls.

## Test Fixtures

Specs import `test` and `expect` from `tests/support/fixtures.ts`, the app's fixtures, which extend
the template's `tests/support/fixtures-infrastructure.ts`.

| Fixture | Type | Description |
| --- | --- | --- |
| `frontendUrl` | `string` | The worker's Vite server, which proxies `/api` — the SSE stream included — to the worker's backend. Also Playwright's `baseURL`. |
| `backendUrl` | `string` | The worker's Flask backend. |
| `backendLogs`, `frontendLogs` | `BackendLogCollector`, `FrontendLogCollector` | Automatic: attach each worker server's output to the test. |
| `sseTimeout` | `number` | 35s timeout for SSE-heavy flows. |
| `page` override | `Page` | Registers the test-event bridge, fails the test on an unexpected `console.error` or page error, and disables motion and animations. |
| `testEvents` | `TestEventCapture` | The test events the app emits in test mode. |
| `toastHelper` | `ToastHelper` | `waitForToast`, `expectSuccessToast`, `expectErrorToast`, `dismissToast` and the like. |
| `fileUploadHelper` | `FileUploadHelper` | Drives file inputs and drop zones. |
| `deploymentSse` | `DeploymentSseHelper` | Connects to and reads the deployment-version SSE stream. |
| `auth` | `AuthFactory` | `createSession({ subject?, name?, email?, roles? })`, `clearSession()`, `forceError(status)` over `/api/testing/auth/*`. |
| `appShell` | `AppShellPage` | The app shell's page object. |
| `deviceModels` | `DeviceModelsFactory` | App fixture; see above. |
| `devices` | `DevicesFactory` | App fixture; see above. |

Feature page objects are not fixtures: `DevicesPage`, `RotationPage` and `AuthPage` live beside their
specs under `tests/e2e/<feature>/`, and a spec constructs its own (`new DevicesPage(page)`). Keep
fixture code minimal; complexity belongs in page objects or factories.

Each worker gets its own services: the internal service manager clones the run's seed database,
then starts a backend and a frontend on free ports.

## The Fake USB Device

Playwright cannot drive the browser's Web Serial port picker, and no suite has an ESP32 to talk to,
so Provision device and Flash device run against a fake port and chip. The design and what each
spec proves are in [Firmware flashing → How it is tested](../../../../docs/firmware-flashing.md#how-it-is-tested).

- **`tests/support/mocks/esptool-mock.ts`** — Vite aliases `esptool-js` to it when
  `VITE_TEST_MODE=true` (`vite.config.ts`). It plays the chip: `ESPLoader`, `Transport` and the reset
  classes, with a flash that reads back what was written, recording every write.
- **`tests/support/mocks/fake-esp-device.ts`**
  - `installFakeEspDevice(page, config?)` – call before the page loads. It replaces
    `navigator.serial` with one whose `requestPort()` hands out a fake port that records the signals
    set on it. `config` is a `Partial<ESPLoaderMockConfig>` over the mock's defaults:
    `connectionResult` (`'success' | 'timeout' | 'error'`), `partitionTable` (`null` for a read
    failure), `flashWriteResult` (`'success' | 'error'`), `verificationResult`
    (`'match' | 'mismatch'`), `chipName` (default `'ESP32-S3'`) and `operationDelayMs`.
  - `readFakeEspDevice(page)` – what the fake device was asked for so far: its `chip` config,
    `portRequests`, and `operations` in order, each a `write` (`address`, `data`, `md5`, `eraseAll`)
    or the `signals` set on the port.

`devices-flashing.spec.ts` and `devices-provisioning.spec.ts` use the pair. The images Flash device
writes come from `deviceModels.seedFirmware()`, so the backend side of the flash is real.

## Backend Testing Endpoints

What no factory seeds, specs drive through the backend's `/api/testing/*` endpoints
(`backend/app/api/testing*.py`), which answer only when the backend runs in testing mode:

- `/api/testing/devices/logs/seed`, `inject`, `subscriptions` and `drop-stream` – device logs and
  their SSE stream
- `/api/testing/rotation/nudge` – the rotation dashboard's SSE update
- `/api/testing/deployments/version`, `/api/testing/sse/task-event`,
  `/api/testing/sse/force-callback-error` – the deployment banner and the SSE infrastructure
- `/api/testing/auth/*`, `/api/testing/keycloak-cleanup` – used by `auth` and the `devices` fixture

## Global Setup and Teardown

- `tests/support/global-setup.ts` creates the run's seed database and loads the backend's test data
  into it (`uv run cli load-test-data`); each worker's backend serves a clone of it. It refuses
  `PLAYWRIGHT_MANAGED_SERVICES=false`: services are always per worker.
- `tests/support/global-teardown.ts` drops the run's databases, best effort.

## Helpers (`tests/support/helpers.ts`)

- `makeUnique(prefix?, length?)`, `makeUniqueToken(length?)` – deterministic-length unique IDs
- `waitTestEvent(page, kind, filter?, timeout?)`, `waitForUiState(...)`, `waitForListLoading(...)`
- `waitForElement(page, selector, timeout?)`
- `waitForFormValidationError(page, formId, field?)`
- `expectConflictError(page, correlationId?)`
- `expectConsoleError(page, pattern)` – registers a console error the `page` fixture lets through
- `emitTestEvent(page, payload)`, `waitForSseEvent(...)` and `extractSseData(event)` from
  `tests/support/helpers/test-events.ts`

Avoid duplicating helper logic in specs — centralize shared behaviors here.

## Random Data Strategy

- Use the factory helpers (e.g., `devices.randomDeviceName('Sensor')`,
  `deviceModels.randomModelCode()`).
- Prefix identifiers with domain-specific tokens to aid debugging.
- Keep randomization deterministic length-wise to avoid UI layout drift.
- Seed fresh data per spec. Even if two tests need identical state, create separate records to avoid hidden coupling.
- `Date.now()` is eslint-blocked—use `makeUnique` or domain helpers for uniqueness, and document any rare inline exemptions where a real timestamp is required.

## Deterministic Testing Content

Use the backend-provided `/api/testing/content/*` endpoints whenever specs need static assets:

- `GET /api/testing/content/image?text=<label>` – stable placeholder PNG.
- `GET /api/testing/content/pdf` – deterministic PDF stream with canned metadata.
- `GET /api/testing/content/html?title=<text>` – plain HTML response without banners.
- `GET /api/testing/content/html-with-banner?title=<text>` – HTML response that includes the standard marketing banner.

Build URLs with the `backendUrl` fixture so the same calls work locally and in CI (swap `localhost` for `127.0.0.1` when necessary so backend validation passes), and avoid hand-rolling data URLs or intercepting document fetches.

## Extending

When a new feature needs coverage:

1. Add the factory method, or a new factory under `tests/api/factories/` that mirrors the domain API.
2. Where the public API cannot seed the state, add a `/api/testing/*` endpoint to the backend rather
   than faking the response.
3. Expose a new factory as a fixture in `tests/support/fixtures.ts`.
4. Put the feature's page object beside its specs under `tests/e2e/<feature>/`.

Document significant additions in this file to keep contributors aligned.

## References

- [Playwright Developer Guide](./playwright_developer_guide.md)
- [Page Objects](./page_objects.md)
- [How to Add an E2E Test](../howto/add_e2e_test.md)
- [Firmware flashing](../../../../docs/firmware-flashing.md)
