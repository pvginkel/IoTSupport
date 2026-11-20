# Contributor Documentation

Welcome! This section is the canonical reference for engineers, QA, and technical writers contributing to the IoT Support frontend: the device models, the devices with their configuration, logs and core dumps, the rotation dashboard, and Flash device and Provision device over USB.

## Audience & Scope

- **Who**: Frontend engineers, automation developers, and documentation contributors.
- **What**: Local setup, environment configuration, testing strategy, instrumentation architecture, and hands-on guides for extending the UI test suite.
- **Why**: Provide a single source of truth so new work follows the implemented patterns without rediscovering tribal knowledge.

## Start Here

- [Getting Started](./getting_started.md) – clone, install, and run the app locally.
- [Environment Reference](./environment.md) – required environment variables and port conventions.
- [Testing Overview](./testing/index.md) – how the Playwright suite is structured and how we keep reruns stable.
- [Add an E2E Test](./howto/add_e2e_test.md) – step-by-step workflow when expanding coverage for a feature.

## Feature Workflow Expectations

1. Instrument first: add or update the test-event emitters your UI change needs — `useListLoadingInstrumentation`, `useUiStateInstrumentation`, `useFormInstrumentation` — before checking in components.
2. Build the UI against those events so loading/error states and toasts are observable through `list_loading`, `ui_state`, `form` and `toast` test events.
3. Extend the Playwright specs in the same change. Coverage must seed data with the `devices` and `deviceModels` factory fixtures, wait on the emitted events, and assert backend-driven state before work is marked complete.

## Testing Deep Dives

- [Testing Overview](./testing/index.md)
- [Playwright Developer Guide](./testing/playwright_developer_guide.md)
- [Selector Patterns](./testing/selector_patterns.md)
- [No-Sleep Patterns](./testing/no_sleep_patterns.md)
- [Error Handling & Validation](./testing/error_handling_and_validation.md)
- [Factories & Fixtures](./testing/factories_and_fixtures.md)
- [Page Objects](./testing/page_objects.md)
- [CI & Execution](./testing/ci_and_execution.md)
- [Troubleshooting](./testing/troubleshooting.md)

## UI Guidelines

- [UI Guidelines Overview](./ui/index.md) – entry point into the Device Models and Devices patterns plus the shared conventions.
- Patterns: [Device Models](./ui/patterns/device_models.md), [Devices](./ui/patterns/devices.md).
- Shared conventions: [Button Labeling Standards](./ui/button_standards.md), [Form Conventions](./ui/forms.md), [Data Display Conventions](./ui/data_display.md), [Tooltip Guidelines](./ui/tooltip_guidelines.md).

## Architecture Notes

- [Test Instrumentation](./architecture/test_instrumentation.md) – test-event taxonomy, emitters, and the scopes the app emits.
- [Application Overview](./architecture/application_overview.md) – the frontend's stack, folder layout, routes, and providers.

All docs assume familiarity with TypeScript, React 19, TanStack Router/Query, and Playwright. When in doubt, align with the patterns documented here and cross-link new material back to this hub.
