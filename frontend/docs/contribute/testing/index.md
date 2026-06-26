# Testing Overview

The Electronics Inventory frontend ships with a Playwright-based end-to-end suite that runs against the real backend. This overview introduces the architecture, philosophy, and folder layout before you dive into the detailed guides.

> **Mandatory coupling:** Every UI slice ships with matching instrumentation and Playwright coverage. If the UI changes, the tests change—no feature is complete until its specs exercise the new events against the real backend.

## Guiding Principles

1. **API-first data setup** – Tests create prerequisite data through API factories; the UI is only used for the behavior under test.
2. **Real backend always** – Specs must exercise the production backend endpoints directly; do not intercept or stub HTTP requests. The `testing/no-route-mocks` ESLint rule enforces this for all Playwright sources. If a scenario needs special behavior, extend the backend with test-friendly hooks instead of mocking—the *only* waiver lives alongside the shared AI analysis helper and documents its backend gap.
3. **Fresh data per test** – Every scenario seeds its own data via factories with randomized identifiers; never reuse records across tests.
4. **Dirty database friendly** – We do not care about accumulated test data. Databases are torn down between runs, so favor clarity over cleanup. If data volume exposes performance issues, treat that as a signal to optimize the backing service.
5. **Page objects over selector maps** – Each feature owns a page object colocated with its tests for readable UI interactions.
6. **No arbitrary waits** – Assertions rely on observable UI state or deterministic events; `waitForTimeout` is banned.
7. **Test-mode instrumentation** – Frontend emits structured test events only when `VITE_TEST_MODE=true`, and Playwright captures them via a dedicated bridge for deterministic assertions.

## Folder Layout

```
tests/
├── api/                # Node-safe API client + factories
├── e2e/                # Feature-focused Playwright specs & page objects
├── support/            # Fixtures, helpers, console/error policies
├── README.md           # Legacy doc (now points here)
└── *.md                # Legacy pattern docs (now moved under docs/contribute)
```

- **Factories & Fixtures**: See [Factories & Fixtures](./factories_and_fixtures.md)
- **Page Objects**: See [Page Objects](./page_objects.md)
- **Selector Strategy**: See [Selector Patterns](./selector_patterns.md)
- **Wait Strategies**: See [No-Sleep Patterns](./no_sleep_patterns.md)

## Test Taxonomy

- `tests/e2e/types/*` – Types feature pilot coverage (CRUD, blocked delete)
- `tests/support/fixtures.ts` – Registers shared fixtures (`testData`, `types`, console guarding, test-event bridge)
- `tests/support/global-setup.ts` – Configures environment before the suite (sets `FRONTEND_URL`, etc.)

As additional features gain coverage, follow the same foldering: keep page objects next to their specs and reuse shared helpers from `tests/support`.

## Performance Guidelines

- Seed complex state through factories instead of long UI flows.
- Prefer specific assertions over broad waits to keep runs fast.
- Avoid duplicate coverage—exercise each backend path once per spec unless a regression requires more.
- Use parallel-safe random data (`prefix-shortId`) so reruns skip costly resets; never reuse data seeded by another test.

## Backend Responsibilities

- When a flow needs deterministic behavior (e.g., AI analysis responses, long-running jobs), add explicit testing hooks to the backend rather than stubbing network calls. For example, the AI analysis SSE endpoint should expose a test trigger that Playwright can seed via the API—for instance, POST a prebaked payload to a testing route and then issue a UI search for a sentinel such as `test-response-12345` to stream that payload back.
- If a feature cannot currently be exercised without interception, treat that as a backend gap. Before any Playwright work begins, add a **Blocking Issues** section at the top of the feature plan that calls out the missing backend support so it can be coordinated and resolved.

## Instrumentation & Signals

- The frontend emits structured test events through the Playwright bridge while in test mode.
- Tests use helpers such as `waitTestEvent` and `expectConsoleError` from `tests/support/helpers.ts`.
- Review [Test Instrumentation](../architecture/test_instrumentation.md) for the precise taxonomy (`route`, `form`, `api`, `toast`, `error`, `query_error`, `ui_state`, `list_loading`, `sse`).

## Next Steps

- Deep dive into the [Playwright Developer Guide](./playwright_developer_guide.md) for detailed workflows.
- When adding coverage, follow the [Add an E2E Test](../howto/add_e2e_test.md) checklist.
- For execution details (headless policy, managed services), see [CI & Execution](./ci_and_execution.md).
