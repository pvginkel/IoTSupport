/**
 * Domain-specific provisioning test event types for ESP32 device flashing.
 * These extend the template's test event system with IoT-specific provisioning events.
 */

/**
 * Provisioning phase for device flashing workflow
 */
export type ProvisioningPhase =
  | 'idle'
  | 'connecting'
  | 'reading_partition'
  | 'fetching_nvs'
  | 'flashing'
  | 'verifying'
  | 'success'
  | 'error';

/**
 * Provisioning lifecycle event for ESP32 device flashing
 */
export interface ProvisioningTestEvent {
  kind: 'provisioning';
  timestamp?: string;
  phase: 'started' | 'progress' | 'complete' | 'error';
  deviceId: number;
  metadata?: {
    provisioningPhase?: ProvisioningPhase;
    progress?: number;
    error?: string;
    [key: string]: unknown;
  };
}
