# UI Guidelines Overview

## About This Suite
This section of the contributor docs captures the UI conventions that every feature plan should reference instead of redefining common knowledge. It complements the architecture snapshot in [Architecture → Application Overview](../architecture/application_overview.md) by focusing on the concrete primitives that appear in the current app: the lightweight **Type Catalog** flow and the multi-surface **Part Management** experience. Treat these pages as the canonical description of how the frontend behaves today; feature plans should only describe what changes.

## How To Use These Docs
1. Start with the **Pattern Library** below and choose the archetype that most closely matches the surface you are touching. Each pattern document calls out required UX states, generated API hooks, and instrumentation contracts.
2. Review the **Shared Building Blocks** docs to confirm whether an idea already has form or data-display conventions. Reuse the existing abstractions before introducing new UI elements.
3. When drafting a plan, cite specific sections (for example, “see UI → Part Management → Implementation Checklist”) and limit the plan to deltas. This keeps plans lean while still giving implementers everything they need.
4. Cross-check your plan against the Playwright guidance in [Testing](../testing/index.md) and [Playwright Developer Guide](../testing/playwright_developer_guide.md) to ensure instrumentation expectations are met.

## Pattern Library
- [Type Catalog Pattern](./patterns/type_catalog.md) – documents the streamlined CRUD experience used by Types and any future “reference data” entities.
- [Part Management Pattern](./patterns/part_management.md) – captures the richer workflow that spans list, detail, AI-assisted creation, attachments, and inventory actions.

## Shared Building Blocks
- [Button Labeling Standards](./button_standards.md) – defines the `<verb> <noun>` pattern, business-function naming, accessibility requirements, and acceptable exceptions for all button labels.
- [Form Conventions](./forms.md) – outlines how to compose dialogs, forms, validation, and instrumentation with `useFormState`, `useFormInstrumentation`, and the UI kit.
- [Data Display Conventions](./data_display.md) – explains list/detail expectations, skeletons, empty states, and `useListLoadingInstrumentation` usage.
- [Tooltip Guidelines](./tooltip_guidelines.md) – documents when to use plain `title` vs the shared `Tooltip` component, automatic disabled element handling, placement modes, and the prohibition on bespoke tooltip implementations.

Use these building-block docs whenever you extend a pattern. They summarize reusable pieces such as `FormLabel`, `Button`, `SearchableSelect`, and list instrumentation so new code stays consistent.

## Related References
- [Contributor Hub](../index.md) for setup, environment, and process guidance.
- [Architecture → Application Overview](../architecture/application_overview.md) for the React 19 + TanStack Router/Query stack and generated API client overview.
- [Testing → Playwright Developer Guide](../testing/playwright_developer_guide.md) and [Testing → Factories & Fixtures](../testing/factories_and_fixtures.md) for real-backend execution rules and selector strategy.
- [Commands → Plan Feature](../../commands/plan_feature.md) (updated to reference this suite) for the template that feature plans should follow.

Re-read these documents whenever you touch the Playwright suite or introduce new UI surface types; they serve as the source of truth for consistency, instrumentation, and implementation detail.
