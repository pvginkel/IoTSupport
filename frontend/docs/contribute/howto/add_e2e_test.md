# How to Add an E2E Test

Follow this procedure whenever you extend Playwright coverage for a new workflow or feature.

## 1. Plan the Scenario

- Identify the user flow and success criteria.
- List prerequisite data (types, parts, boxes, etc.).
- Confirm instrumentation exists for key signals (forms, toasts). If not, plan to add it.
- Review [Testing Overview](../testing/) to ensure the scenario fits existing patterns.

## 2. Prepare Factories & API Support

- Check `tests/api/factories/*` for helpers that can create the required entities.
- Add new factory methods or new factories if the backend lacks coverage.
- Keep randomization consistent with the prefix-shortId strategy.
- Update [Factories & Fixtures](../testing/factories_and_fixtures.md) if you add reusable helpers.

## 3. Create or Update Page Objects

- Add a page object under `tests/e2e/<feature>/` (see [Page Objects](../testing/page_objects.md)).
- Expose locators/actions for the UI elements you will touch.
- Update `tests/support/fixtures.ts` to expose the page object if multiple specs will use it.

## 4. Instrument the UI (if needed)

- Ensure forms emit `trackForm*` events and validation errors use `trackFormValidationError(s)`.
- Add `data-testid` attributes where semantic selectors are insufficient.
- Verify instrumentation is behind `isTestMode()`.
- Document new signals in [Test Instrumentation](../architecture/test_instrumentation.md) if you introduce them.

## 5. Write the Spec

- Place the spec next to the feature (`tests/e2e/<feature>/<scenario>.spec.ts`).
- Import fixtures: `import { test, expect } from '../support/fixtures';`
- Use factories for setup, page objects for interactions, and `expect`/test-event helpers for assertions.
- Avoid fixed sleeps—follow [No-Sleep Patterns](../testing/no_sleep_patterns.md).
- Mark expected console errors with `expectConsoleError` when necessary.

## 6. Run & Iterate

```bash
pnpm playwright test tests/e2e/<feature>/<scenario>.spec.ts
```

- Use `--debug` to inspect flaky selectors or waits.
- Review the Playwright HTML report if the test fails.

## 7. Update Documentation & Links

- Reference new helper methods or page objects in the relevant docs if they represent reusable patterns.
- Ensure any moved material links back to the canonical pages under `docs/contribute/`.

## 8. Commit & Review

- Keep specs, page objects, and factories in the same commit for easier review.
- Mention any new instrumentation or environment changes in the PR description.

Following this checklist keeps new tests aligned with the API-first, dirty-DB, and instrumentation-driven strategy described across the contributor docs.
