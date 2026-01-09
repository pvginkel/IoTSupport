# UI Component Refactoring Workflow

## Overview

This document describes an automated, iterative workflow for extracting reusable, **semantically meaningful** UI components into `src/components/ui/`. The goal is to create components that represent clear UI concepts, not just CSS wrappers. These components centralize styling and behavior for specific UI patterns, leaving domain-specific components free of styling classes.

**Important**: This workflow is for extracting components with clear semantic meaning—components that answer "**what is this?**" rather than "**how is this styled?**"

## Principles

1. **Semantic Meaning First**: Components must represent clear UI concepts with semantic names. Ask "what is this?" not "how is this laid out?" Valid: `StatusBadge`, `EmptyState`, `GridTileCard`. Invalid: `FlexRow`, `DivWithPadding`, `ButtonGroup`.
2. **Prefer High-Level Abstractions**: When possible, extract complete UI concepts (like "card with actions") rather than many small composable pieces. One `GridTileCard` component is better than composing `Card` + `CardHeader` + `CardContent` + `ActionButtonGroup`.
3. **Encapsulation**: All styling lives in `components/ui`. Reusable components do NOT expose `className` props.
4. **Generic Design**: UI components must be domain-agnostic. No kit-specific or shopping-list-specific logic in `components/ui`.
5. **Pragmatic Standardization**: Minor visual differences (padding, spacing) across similar components are acceptable casualties. Standardize using common sense.
6. **Single Component per Iteration**: Each workflow run targets exactly one well-defined component type.
7. **Unattended Execution**: The workflow should complete without user intervention for typical refactoring work.
8. **Aggressive Cleanup**: This is technical debt elimination. Make breaking changes. Remove `className` props completely—do NOT keep them as deprecated or no-op parameters. Let TypeScript and tests catch all affected call sites. Fix breaking changes as they arise.

## Workflow Steps

### 0. Establish Feature Directory

**Before invoking any agents**, determine the feature directory path where all planning documents will be stored:

```
docs/features/<FEATURE_NAME>/
```

Where `<FEATURE_NAME>` is a snake_case identifier for the component being extracted (e.g., `link_chip_extraction`, `status_badge_refactor`).

Create this directory using `mkdir -p docs/features/<FEATURE_NAME>/` before proceeding.

**Document Paths**:
- Plan: `docs/features/<FEATURE_NAME>/plan.md`
- Plan Review: `docs/features/<FEATURE_NAME>/plan_review.md`
- Code Review: `docs/features/<FEATURE_NAME>/code_review.md`

You will provide these **explicit full paths** to every agent invocation in the following steps.

### 1. Identify a Component

Pick a single, clearly specified component to extract. The component must have **semantic meaning** and represent a clear UI concept.

**Valid Component Examples** (semantic, represent clear UI concepts):
- **StatusBadge** — Displays the status of an item (semantic: it shows status)
- **InformationBadge** — Displays a piece of information with an icon (semantic: informational badge)
- **EmptyState** — Represents the empty state of a list or view (semantic: empty state)
- **LinkChip** — A chip that links to another page (semantic: navigational chip)
- **GridTileCard** — A card used in grid layouts with title, actions, and content (semantic: card concept)
- **FormFieldGroup** — Groups related form fields with consistent layout (semantic: form grouping)

**Invalid Component Examples** (NOT semantic, just CSS wrappers or too simple):
- **FlexRow** — Just a flex container (describes layout, not meaning)
- **ActionButtonGroup** — Too simple, just groups buttons without real semantic value
- **DivWithPadding** — Pure CSS wrapper with no semantic meaning
- **TextMuted** — Just a color utility, not a UI concept

**Selection Criteria**:
1. **Semantic test**: Does the component name answer "what is this?" rather than "how is this styled?"
2. **Abstraction level**: Prefer high-level abstractions that encapsulate complete concepts over small building blocks
3. **Domain-agnostic**: Component must work across multiple domains without domain-specific logic
4. **Clear boundaries**: Should have well-defined visual and behavioral boundaries
5. **Reusability**: Prefer components with multiple usages OR clear patterns worth standardizing

**Selection Process**:
- Do a thorough search of the codebase to find candidates
- Select at least three candidates
- From these three, pick the one that:
  - Has the clearest semantic meaning
  - Has the most use cases OR abstracts away the most UI complexity
  - Represents a complete concept (prefer high-level over low-level)

### 2. Create a Plan

Use the `plan-writer` agent to create a detailed implementation plan:

```
Use the Task tool with the plan-writer agent to create a plan for extracting [COMPONENT_NAME] into a reusable UI component in src/components/ui/.

The plan should:
- Identify all current usages of this pattern in the codebase
- Specify the component API (props, variants, etc.) WITHOUT a className prop
- Detail the styling that will be encapsulated
- Outline the refactoring steps for each usage
- Include Playwright test updates if the component has test coverage
- Address any visual standardization decisions
- Plan to REMOVE className props from domain-specific wrappers completely (not deprecate, REMOVE)

Since this is technical debt work, resolve all questions autonomously. Accept minor visual differences as acceptable losses for consistency. Make breaking changes—do not attempt backward compatibility.

Write the plan to: docs/features/<FEATURE_NAME>/plan.md
```

**Important**: Provide the explicit full path to the plan file in your agent prompt (e.g., `docs/features/link_chip_extraction/plan.md`).

### 3. Review the Plan

Use the `plan-reviewer` agent to validate the plan:

```
Use the Task tool with the plan-reviewer agent to review the plan at docs/features/<FEATURE_NAME>/plan.md.

The review output will be written to: docs/features/<FEATURE_NAME>/plan_review.md

Apply the output to improve the plan. If significant changes are needed, run the plan-reviewer again to validate the updated plan.
```

**Important**: Provide explicit full paths to both the plan and plan review files in your agent prompt (e.g., `docs/features/link_chip_extraction/plan.md` and `docs/features/link_chip_extraction/plan_review.md`).

**Iteration Rule**: If the review suggests substantial changes, update the plan and re-review. Repeat until the plan passes review without major concerns.

### 4. Execute the Plan

The workflow to execute a plan and review the results is written up in `docs/plan_execution_workflow.md`. Use the workflow in that document to execute the plan you created.

## Completion Criteria

The workflow is complete when:
- [ ] Feature directory created at `docs/features/<FEATURE_NAME>/`
- [ ] New UI component exists in `src/components/ui/`
- [ ] All identified usages are refactored
- [ ] No styling classes remain in domain components (for this pattern)
- [ ] The UI component does NOT expose `className` prop
- [ ] Domain-specific wrappers do NOT have `className` props in their interfaces
- [ ] No call sites pass `className` props to the refactored components
- [ ] `pnpm check` passes with zero errors
- [ ] All Playwright tests pass
- [ ] Planning documents created in feature directory (`plan.md`, `plan_review.md`, `code_review.md`, `plan_execution_report.md`)
- [ ] Changes are ready for manual commit outside the sandbox

## Abort Conditions

Abort and request user intervention if:
- **The component lacks clear semantic meaning** — if you can't explain what it is (only how it's styled), it's probably not a valid component
- **The component is just a CSS utility wrapper** — pure layout primitives (flex containers, spacing wrappers) are not appropriate
- **The component is too simple without semantic value** — very basic composition helpers may not be worth the abstraction
- The component requires domain-specific logic that cannot be generalized
- Visual differences are too significant to standardize without design input
- Test failures indicate functional regressions beyond styling changes
- The component's API becomes too complex or unclear

## Example Invocation

To execute one iteration of this workflow:

```
Follow docs/ui_component_workflow.md to extract a reusable UI component.

First, establish the feature directory (e.g., docs/features/link_chip_extraction/).

Then, pick a component, create a plan with explicit paths, review the plan, execute it, review the code, and verify everything passes.

Provide explicit full paths to all planning documents (plan.md, plan_review.md, code_review.md, plan_execution_report.md) when working through the workflow.

Complete the entire workflow unattended unless intervention is required.
```

## Notes

- **Semantic Components Only**: Only extract components with clear semantic meaning. If the component name describes styling (FlexRow, DivWithPadding) rather than purpose (StatusBadge, EmptyState), it's not a valid component.
- **Prefer Higher-Level Abstractions**: One complete abstraction (GridTileCard) is better than many small pieces (Card + CardHeader + ActionButtonGroup). Look for complete UI concepts to extract.
- **Small Semantic Components Are Valid**: Small components like StatusBadge, InformationBadge, and EmptyState are fine—they're small but semantically meaningful. The issue is not size, it's semantic clarity.
- **Incremental Progress**: Each run handles one component type. Repeat this workflow until all styling is centralized in semantic components.
- **Loss of Customization**: This is intentional. We are removing the ability to pass `className` props and other styling customizations. Visual standardization is a feature, not a bug. Components will look consistent across the application.
- **Breaking Changes Are Good**: Type errors from removed props are the mechanism for discovering all usages. Embrace them as a verification tool.
- **Test-Driven**: Update Playwright tests alongside UI changes to maintain coverage.
- **Documentation**: The generated `plan.md`, `code_review.md`, and `plan_execution_report.md` serve as audit trails for each iteration.
- **No Backward Compatibility**: Do not attempt to maintain backward compatibility by keeping deprecated props. Remove them completely and fix all breaking changes.

## Related Documentation

- `CLAUDE.md` — Project instructions and verification requirements
- `docs/plan_execution_workflow.md` — Plan execution and code review workflow
- `docs/contribute/architecture/application_overview.md` — Architecture patterns
- `docs/commands/plan_feature.md` — Feature planning template
- `docs/commands/review_plan.md` — Plan review criteria
- `docs/commands/code_review.md` — Code review standards
