# How to Add an E2E Test

Follow this procedure whenever you extend Playwright coverage for a new workflow or feature.

## 1. Plan the Scenario

- Identify the user flow and success criteria.
- List prerequisite data: device models, devices, a model's firmware, core dumps, device logs.
- Confirm instrumentation exists for key signals (forms, lists, toasts, the flash and provisioning workflows). If not, plan to add it.
- Review the [Testing Overview](../testing/index.md) to ensure the scenario fits existing patterns.

## 2. Prepare Factories & API Support

- Check `tests/api/factories/` (`devices.ts`, `device-models.ts`) for helpers that can create the required data.
- Add new factory methods if they are missing. Where the public API cannot seed the state, add a `/api/testing/*` endpoint to the backend (`backend/app/api/testing*.py`) and wrap it in a factory method.
- Keep randomization consistent with the factories' `random*` helpers and `makeUnique`.
- Update [Factories & Fixtures](../testing/factories_and_fixtures.md) if you add reusable helpers or testing endpoints.

## 3. Create or Update Page Objects

- Add or extend the page object beside the specs under `tests/e2e/<feature>/`, such as `tests/e2e/devices/DevicesPage.ts` (see [Page Objects](../testing/page_objects.md)).
- Expose locators/actions for the UI elements you will touch.
- Specs construct the page object themselves (`new DevicesPage(page)`); it is not a fixture.

## 4. Instrument the UI (if needed)

- Ensure forms emit their events through `useFormInstrumentation` and validation errors use `trackFormValidationError(s)`.
- Ensure lists emit `list_loading` events through `useListLoadingInstrumentation`.
- Add `data-testid` attributes where semantic selectors are insufficient.
- Verify instrumentation is behind `isTestMode()`.
- Document new signals in [Test Instrumentation](../architecture/test_instrumentation.md) if you introduce them.

## 5. Write the Spec

- Place the spec next to the feature (`tests/e2e/<feature>/<scenario>.spec.ts`).
- Import fixtures: `import { test, expect } from '../../support/fixtures';`
- Use factories for setup, page objects for interactions, and `expect`/test-event helpers for assertions.
- For Flash device or Provision device, install the fake USB device before the page loads (see [Factories & Fixtures → The Fake USB Device](../testing/factories_and_fixtures.md#the-fake-usb-device)).
- Avoid fixed sleeps—follow [No-Sleep Patterns](../testing/no_sleep_patterns.md).
- Mark expected console errors with `expectConsoleError` when necessary.

## 6. Run & Iterate

```bash
cexec modern-app pnpm playwright test tests/e2e/<feature>/<scenario>.spec.ts
```

- Run it from `frontend/`.
- Use `--debug` or `--trace on` to inspect flaky selectors or waits.
- Review the Playwright HTML report if the test fails.
- Run `kc project lint frontend` from the repository root.

## 7. Update Documentation & Links

- Add the spec to the Test Taxonomy in the [Testing Overview](../testing/index.md).
- Reference new helper methods or page objects in the relevant docs if they represent reusable patterns.
- Ensure any moved material links back to the canonical pages under `docs/contribute/`.

## 8. Commit & Review

- Keep specs, page objects, and factories in the same commit for easier review.
- Mention any new instrumentation, testing endpoint or environment change in the commit message.

Following this checklist keeps new tests aligned with the API-first, dirty-DB, and instrumentation-driven strategy described across the contributor docs.
