/**
 * Test event type definitions for Playwright instrumentation
 * Phase A: Minimal type stubs
 * Phase B: Full implementation with event emission
 */

export type TestEventKind = 'router' | 'list_loading' | 'form'

export interface BaseTestEvent {
  kind: TestEventKind
  timestamp: number
}

export interface RouterEvent extends BaseTestEvent {
  kind: 'router'
  from: string
  to: string
}

/**
 * Stub type for Phase B
 * Will be used to track list loading states (loading, ready, error)
 */
export interface ListLoadingEvent extends BaseTestEvent {
  kind: 'list_loading'
  phase: 'loading' | 'ready' | 'error'
  listId: string
  itemCount?: number
}

/**
 * Stub type for Phase B
 * Will be used to track form submission lifecycle
 */
export interface FormEvent extends BaseTestEvent {
  kind: 'form'
  phase: 'submit' | 'success' | 'error'
  formId: string
}

export type TestEvent = RouterEvent | ListLoadingEvent | FormEvent
