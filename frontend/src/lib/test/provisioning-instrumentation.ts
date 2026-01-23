/**
 * Provisioning instrumentation hooks for test events.
 * Provides structured provisioning lifecycle events for Playwright test infrastructure.
 */

import { useCallback } from 'react';
import { emitTestEvent } from './event-emitter';
import { TestEventKind, type ProvisioningTestEvent, type ProvisioningPhase } from '@/types/test-events';
import { isTestMode } from '@/lib/config/test-mode';

/**
 * Emit a provisioning lifecycle event when in test mode.
 */
function emitProvisioningEvent(
  deviceId: number,
  phase: ProvisioningTestEvent['phase'],
  metadata?: ProvisioningTestEvent['metadata']
): void {
  if (!isTestMode()) {
    return;
  }

  const payload: Omit<ProvisioningTestEvent, 'timestamp'> = {
    kind: TestEventKind.PROVISIONING,
    deviceId,
    phase,
    ...(metadata ? { metadata } : {}),
  };

  emitTestEvent(payload);
}

/**
 * Track when provisioning workflow starts.
 */
export function trackProvisioningStarted(deviceId: number): void {
  emitProvisioningEvent(deviceId, 'started');
}

/**
 * Track provisioning progress updates.
 */
export function trackProvisioningProgress(
  deviceId: number,
  provisioningPhase: ProvisioningPhase,
  progress: number
): void {
  emitProvisioningEvent(deviceId, 'progress', { provisioningPhase, progress });
}

/**
 * Track when provisioning completes successfully.
 */
export function trackProvisioningComplete(deviceId: number): void {
  emitProvisioningEvent(deviceId, 'complete');
}

/**
 * Track when provisioning fails.
 */
export function trackProvisioningError(
  deviceId: number,
  provisioningPhase: ProvisioningPhase,
  error: string
): void {
  emitProvisioningEvent(deviceId, 'error', { provisioningPhase, error });
}

interface ProvisioningInstrumentationHandlers {
  /** Call when provisioning workflow starts */
  trackStarted: () => void;
  /** Call on progress updates */
  trackProgress: (provisioningPhase: ProvisioningPhase, progress: number) => void;
  /** Call when provisioning completes successfully */
  trackComplete: () => void;
  /** Call when provisioning fails */
  trackError: (provisioningPhase: ProvisioningPhase, error: string) => void;
}

/**
 * Hook to instrument provisioning lifecycle events for Playwright tests.
 * Provides handlers for started/progress/complete/error phases.
 *
 * @example
 * ```tsx
 * const { trackStarted, trackProgress, trackComplete, trackError } = useProvisioningInstrumentation(deviceId);
 *
 * const handleProvision = async () => {
 *   trackStarted();
 *   try {
 *     trackProgress('connecting', 5);
 *     await connectToDevice();
 *     trackProgress('reading_partition', 15);
 *     await readPartitionTable();
 *     // ... more steps
 *     trackComplete();
 *   } catch (err) {
 *     trackError('connecting', err.message);
 *   }
 * };
 * ```
 */
export function useProvisioningInstrumentation(
  deviceId: number | undefined
): ProvisioningInstrumentationHandlers {
  const trackStarted = useCallback(() => {
    if (deviceId !== undefined) {
      trackProvisioningStarted(deviceId);
    }
  }, [deviceId]);

  const trackProgress = useCallback(
    (provisioningPhase: ProvisioningPhase, progress: number) => {
      if (deviceId !== undefined) {
        trackProvisioningProgress(deviceId, provisioningPhase, progress);
      }
    },
    [deviceId]
  );

  const trackComplete = useCallback(() => {
    if (deviceId !== undefined) {
      trackProvisioningComplete(deviceId);
    }
  }, [deviceId]);

  const trackError = useCallback(
    (provisioningPhase: ProvisioningPhase, error: string) => {
      if (deviceId !== undefined) {
        trackProvisioningError(deviceId, provisioningPhase, error);
      }
    },
    [deviceId]
  );

  return {
    trackStarted,
    trackProgress,
    trackComplete,
    trackError,
  };
}
