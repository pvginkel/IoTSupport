/**
 * Router instrumentation setup for test mode
 * Stub for Phase A - will be expanded in Phase B
 *
 * TODO(Phase B): Implement router event emission to track navigation
 * Should:
 * - Subscribe to TanStack Router's navigation events
 * - Emit RouterEvent with 'from' and 'to' paths when navigation completes
 * - Track route transitions for Playwright tests to wait on
 * - Include both programmatic and user-initiated navigations
 *
 * @see docs/features/phase_a_foundation/plan.md (Slice 7 - Test Events)
 */

import type { Router } from '@tanstack/react-router'

export function setupRouterInstrumentation(router: Router<any, any>) {
  // Stub implementation for Phase A
  // Full implementation in Phase B
  void router // unused in Phase A
}
