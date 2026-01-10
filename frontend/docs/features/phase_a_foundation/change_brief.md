# Phase A: Foundation & Test Infrastructure - Change Brief

## Overview

Set up the IoT Support frontend application foundation including project scaffolding, app shell with sidebar, and complete Playwright test infrastructure. This phase must be fully working before feature implementation begins.

## Scope

### A1. Project Scaffolding
- Initialize package.json with React 19, TypeScript, Vite, TanStack Router/Query, Tailwind CSS 4, Radix UI, Monaco Editor, openapi-fetch
- Configure Vite with API proxy to localhost:3201, dev server on port 3200, test mode handling
- Set up TypeScript strict mode, ESLint, Prettier
- Create API generation pipeline (copy from ElectronicsInventory)

### A2. App Shell
- Create dark mode app shell with fixed sidebar
- Sidebar has "IoT Support" branding and single "Device Configs" navigation item
- Basic routing: root redirects to /devices, placeholder device list page
- Test IDs on shell components for Playwright

### A3. Playwright Test Infrastructure
- Per-worker service isolation (backend + frontend per worker)
- Service management with health check polling
- Test event system (isTestMode, event emitter, event capture)
- API factories for creating test configs
- Page objects for device interactions
- Smoke tests validating the setup works

## Success Criteria

- `pnpm check` passes
- `pnpm build` succeeds
- `pnpm dev` starts frontend on port 3200
- `pnpm playwright test tests/smoke.spec.ts` passes
- Services start/stop cleanly per worker
- API factories create/delete configs successfully

## Reference Documents

- Product Brief: `docs/product_brief.md`
- Implementation Plan: `docs/implementation_plan.md`
- Playwright Implementation Plan: `docs/playwright_implementation_plan.md`
