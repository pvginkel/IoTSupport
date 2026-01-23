/**
 * Form instrumentation hooks for test events.
 * Provides structured form lifecycle events for Playwright test infrastructure.
 */

import { useCallback, useEffect, useRef } from 'react';
import { emitTestEvent } from './event-emitter';
import { TestEventKind, type FormTestEvent } from '@/types/test-events';
import { isTestMode } from '@/lib/config/test-mode';

/**
 * Emit a form lifecycle event when in test mode.
 */
function emitFormEvent(
  formId: string,
  phase: FormTestEvent['phase'],
  fields?: Record<string, unknown>,
  metadata?: FormTestEvent['metadata']
): void {
  if (!isTestMode()) {
    return;
  }

  const payload: Omit<FormTestEvent, 'timestamp'> = {
    kind: TestEventKind.FORM,
    formId,
    phase,
    ...(fields ? { fields } : {}),
    ...(metadata ? { metadata } : {}),
  };

  emitTestEvent(payload);
}

/**
 * Track when a form is opened/mounted.
 */
export function trackFormOpen(formId: string, fields?: Record<string, unknown>): void {
  emitFormEvent(formId, 'open', fields);
}

/**
 * Track when a form is submitted.
 */
export function trackFormSubmit(formId: string, fields?: Record<string, unknown>): void {
  emitFormEvent(formId, 'submit', fields);
}

/**
 * Track when a form submission succeeds.
 */
export function trackFormSuccess(formId: string, fields?: Record<string, unknown>): void {
  emitFormEvent(formId, 'success', fields);
}

/**
 * Track when a form submission fails.
 */
export function trackFormError(
  formId: string,
  error?: string,
  fields?: Record<string, unknown>
): void {
  emitFormEvent(formId, 'error', fields, error ? { error } : undefined);
}

/**
 * Track when a form validation error occurs.
 */
export function trackFormValidationError(
  formId: string,
  field: string,
  error: string,
  fields?: Record<string, unknown>
): void {
  emitFormEvent(formId, 'validation_error', fields, { field, error });
}

interface UseFormInstrumentationOptions {
  /** Unique identifier for the form, used in test-event payloads */
  formId: string;
  /** Whether the form is currently open/mounted */
  isOpen?: boolean;
}

interface FormInstrumentationHandlers {
  /** Call when form submission starts */
  trackSubmit: (fields?: Record<string, unknown>) => void;
  /** Call when form submission succeeds */
  trackSuccess: (fields?: Record<string, unknown>) => void;
  /** Call when form submission fails */
  trackError: (error?: string, fields?: Record<string, unknown>) => void;
  /** Call when a field validation error occurs */
  trackValidationError: (field: string, error: string, fields?: Record<string, unknown>) => void;
}

/**
 * Hook to instrument form lifecycle events for Playwright tests.
 * Emits 'open' event on mount and provides handlers for submit/success/error phases.
 *
 * @example
 * ```tsx
 * const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({
 *   formId: 'DeviceEditor',
 *   isOpen: true
 * });
 *
 * const handleSave = async () => {
 *   trackSubmit({ deviceId });
 *   try {
 *     await saveDevice();
 *     trackSuccess({ deviceId });
 *   } catch (err) {
 *     trackError(err.message);
 *   }
 * };
 * ```
 */
export function useFormInstrumentation(
  options: UseFormInstrumentationOptions
): FormInstrumentationHandlers {
  const { formId, isOpen = true } = options;
  const hasEmittedOpenRef = useRef(false);
  const testMode = isTestMode();

  // Emit 'open' event when the form is first mounted
  // Using useEffect to properly handle the side effect and ref access
  useEffect(() => {
    if (!testMode) {
      return;
    }

    if (isOpen && !hasEmittedOpenRef.current) {
      hasEmittedOpenRef.current = true;
      trackFormOpen(formId);
    } else if (!isOpen) {
      // Reset when form is closed
      hasEmittedOpenRef.current = false;
    }
  }, [formId, isOpen, testMode]);

  const trackSubmit = useCallback(
    (fields?: Record<string, unknown>) => {
      trackFormSubmit(formId, fields);
    },
    [formId]
  );

  const trackSuccess = useCallback(
    (fields?: Record<string, unknown>) => {
      trackFormSuccess(formId, fields);
    },
    [formId]
  );

  const trackError = useCallback(
    (error?: string, fields?: Record<string, unknown>) => {
      trackFormError(formId, error, fields);
    },
    [formId]
  );

  const trackValidationError = useCallback(
    (field: string, error: string, fields?: Record<string, unknown>) => {
      trackFormValidationError(formId, field, error, fields);
    },
    [formId]
  );

  return {
    trackSubmit,
    trackSuccess,
    trackError,
    trackValidationError,
  };
}
