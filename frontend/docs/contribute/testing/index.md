# Testing Overview

The IoT Support frontend ships with a Playwright end-to-end suite that runs against the real backend. This overview introduces the architecture, philosophy, and folder layout before you dive into the detailed guides.

> **Mandatory coupling:** Every UI slice ships with matching instrumentation and Playwright coverage. If the UI changes, the tests change—no feature is complete until its specs exercise the new events against the real backend.

## Guiding Principles

1. **API-first data setup** – Tests create prerequisite data through the `devices` and `deviceModels` factories; the UI is only used for the behavior under test.
2. **Real backend always** – Specs must exercise the real backend endpoints; do not intercept or stub HTTP requests. The `testing/no-route-mocks` ESLint rule enforces this for all Playwright sources. If a scenario needs special behavior, extend the backend with a `/api/testing/*` endpoint instead of mocking.
3. **One stand-in, for the hardware** – The suite fakes only what no test can reach: the USB serial port and the ESP32 behind it, for Flash device and Provision device. Vite aliases `esptool-js` to a mock in test mode, and `installFakeEspDevice`/`readFakeEspDevice` drive it; every request still goes to the real backend. See [Factories & Fixtures → The Fake USB Device](./factories_and_fixtures.md#the-fake-usb-device) and [Firmware flashing → How it is tested](../../../../docs/firmware-flashing.md#how-it-is-tested).
4. **Fresh data per test** – Every scenario seeds its own data via factories with randomized identifiers; never reuse records across tests.
5. **Dirty database friendly** – We do not care about accumulated test data. Each worker's backend serves a clone of the run's seed database, and global teardown drops them, so favor clarity over cleanup. If data volume exposes performance issues, treat that as a signal to optimize the backing service.
6. **Page objects over selector maps** – Each feature owns a page object colocated with its tests for readable UI interactions.
7. **No arbitrary waits** – Assertions rely on observable UI state or deterministic events; `waitForTimeout` is banned.
8. **Test-mode instrumentation** – The frontend emits structured test events only when `VITE_TEST_MODE=true`, and Playwright captures them via a dedicated bridge for deterministic assertions.

## Folder Layout

```
tests/
├── api/                # Node-safe API client + factories (devices, device models)
├── e2e/                # The app's feature specs, each beside its page object
│   ├── auth/
│   ├── devices/
│   └── rotation/
├── infrastructure/     # The template's specs: auth, app shell, SSE, deployment banner, toasts, test-event bridge
├── support/            # Fixtures, helpers, page objects, per-worker services
│   ├── helpers/        # Auth, deployment SSE, file upload, test events, toasts, database admin
│   ├── mocks/          # esptool-js mock and the fake USB device
│   ├── page-objects/   # App shell and base page
│   └── process/        # Per-worker backend and frontend servers and their logs
└── smoke.spec.ts       # App shell, root redirect, backend health through the proxy
```

- **Factories & Fixtures**: See [Factories & Fixtures](./factories_and_fixtures.md)
- **Page Objects**: See [Page Objects](./page_objects.md)
- **Selector Strategy**: See [Selector Patterns](./selector_patterns.md)
- **Wait Strategies**: See [No-Sleep Patterns](./no_sleep_patterns.md)

`tests/infrastructure/**` and `tests/support/` come from the frontend template and change through `copier update`, except `tests/support/fixtures.ts` and `tests/support/selectors-domain.ts`, which the template generates once and the app owns. The app's own code is `tests/api/`, `tests/e2e/`, `tests/support/mocks/`, those two files and `smoke.spec.ts`.

## Test Taxonomy

- `tests/e2e/devices/devices-crud.spec.ts` – the device list; creating, editing, duplicating and deleting a device; unsaved changes, sorting and the active toggle
- `tests/e2e/devices/devices-tabs.spec.ts` – the device's tabs and their deep links
- `tests/e2e/devices/devices-flashing.spec.ts` – Flash device over the fake USB device
- `tests/e2e/devices/devices-provisioning.spec.ts` – Provision device over the fake USB device, and the provisioning modal
- `tests/e2e/devices/devices-logs.spec.ts`, `devices-logs-sse.spec.ts` – the Logs tab, its backfill and download, and its live SSE stream
- `tests/e2e/devices/devices-coredumps.spec.ts` – the core dumps table
- `tests/e2e/rotation/rotation-sse.spec.ts` – the rotation dashboard and its SSE nudge
- `tests/e2e/auth/auth.spec.ts` – loading state, login redirect, auth errors, the signed-in user and logout
- `tests/support/fixtures.ts` – the app's fixtures (`devices`, `deviceModels`) over the template's `fixtures-infrastructure.ts` (per-worker services, console guarding, test-event bridge, `auth`, `toastHelper`, `deploymentSse` and the like)
- `tests/support/global-setup.ts` – creates the run's seed database and loads the backend's test data into it

As additional features gain coverage, follow the same foldering: put specs and their page object under `tests/e2e/<feature>/` and reuse shared helpers from `tests/support`.

## Performance Guidelines

- Seed complex state through factories instead of long UI flows.
- Prefer specific assertions over broad waits to keep runs fast.
- Avoid duplicate coverage—exercise each backend path once per spec unless a regression requires more.
- Use parallel-safe random data (the factories' `random*` helpers, `makeUnique`) so reruns skip costly resets; never reuse data seeded by another test.

## Backend Responsibilities

- When a flow needs state the public API cannot seed or an event it cannot trigger on demand, add a testing endpoint to the backend (`backend/app/api/testing*.py`, answering only in testing mode) rather than stubbing network calls. The suite already drives:
  - `/api/testing/device-models/{model_id}/firmware` – a model's current firmware, flashable or not (`deviceModels.seedFirmware()`)
  - `/api/testing/coredumps` – a device's core dumps (`devices.createCoredump()`)
  - `/api/testing/devices/logs/*` – device logs and their SSE stream
  - `/api/testing/rotation/nudge` – the rotation dashboard's SSE update
  - `/api/testing/auth/*`, `/api/testing/keycloak-cleanup` – sessions and per-worker Keycloak cleanup

  [Factories & Fixtures → Backend Testing Endpoints](./factories_and_fixtures.md#backend-testing-endpoints) has the full list.
- If a feature cannot currently be exercised without interception, treat that as a backend gap. Before any Playwright work begins, add a **Blocking Issues** section at the top of the feature plan that calls out the missing backend support so it can be coordinated and resolved.

## Instrumentation & Signals

- The frontend emits structured test events through the Playwright bridge while in test mode.
- Tests use helpers such as `waitTestEvent` and `expectConsoleError` from `tests/support/helpers.ts`.
- Review [Test Instrumentation](../architecture/test_instrumentation.md) for the precise taxonomy (`route`, `form`, `api`, `toast`, `error`, `query_error`, `ui_state`, `list_loading`, `sse`, and the app's own `provisioning`).

## Next Steps

- Deep dive into the [Playwright Developer Guide](./playwright_developer_guide.md) for detailed workflows.
- When adding coverage, follow the [Add an E2E Test](../howto/add_e2e_test.md) checklist.
- For execution details (headless policy, managed services), see [CI & Execution](./ci_and_execution.md).
