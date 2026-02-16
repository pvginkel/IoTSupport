import { ulid } from 'ulid';
import type { Page } from '@playwright/test';
import { createApiClient, createPlaywrightFetch, apiRequest, type ApiClient } from '../client';
import { DeviceModelsFactory } from './device-models';

export interface DeviceFactoryOptions {
  deviceModelId?: number;
  deviceName?: string;
  deviceEntityId?: string;
  enableOta?: boolean;
  config?: Record<string, unknown>;
}

export interface CreatedDevice {
  id: number;
  key: string;
  deviceModelId: number;
  config: string;
  deviceName: string | null;
  deviceEntityId: string | null;
  enableOta: boolean | null;
  rotationState: string;
  clientId: string;
}

export interface CoredumpFactoryOptions {
  deviceId: number;
  chip?: string;
  firmwareVersion?: string;
  size?: number;
  parseStatus?: string;
  parsedOutput?: string | null;
}

export interface CreatedCoredump {
  id: number;
  deviceId: number;
  chip: string;
  firmwareVersion: string;
  size: number;
  parseStatus: string;
  parsedOutput: string | null;
  parsedAt: string | null;
  uploadedAt: string;
  createdAt: string;
  updatedAt: string;
}

export class DevicesFactory {
  private client: ApiClient;
  private deviceModelsFactory: DeviceModelsFactory;

  constructor(baseUrl: string, page: Page) {
    // Use Playwright's request context for cookie sharing with the browser
    this.client = createApiClient({
      baseUrl,
      fetch: createPlaywrightFetch(page.request),
    });
    this.deviceModelsFactory = new DeviceModelsFactory(baseUrl, page);
  }

  /**
   * Generate a random device name for testing
   */
  randomDeviceName(prefix = 'Test Device'): string {
    const suffix = ulid().slice(0, 6);
    return `${prefix} ${suffix}`;
  }

  /**
   * Generate a random device entity ID for testing
   */
  randomDeviceEntityId(prefix = 'test_device'): string {
    const suffix = ulid().toLowerCase().slice(0, 8);
    return `${prefix}_${suffix}`;
  }

  /**
   * Create a device
   * If no deviceModelId is provided, creates a new device model first
   */
  async create(options: DeviceFactoryOptions = {}): Promise<CreatedDevice> {
    // If no model ID provided, create a model first
    let deviceModelId = options.deviceModelId;
    if (!deviceModelId) {
      const model = await this.deviceModelsFactory.create();
      deviceModelId = model.id;
    }

    // Build config object
    const config: Record<string, unknown> = options.config ?? {
      deviceName: options.deviceName ?? this.randomDeviceName(),
      deviceEntityId: options.deviceEntityId ?? this.randomDeviceEntityId(),
      enableOTA: options.enableOta ?? false,
    };

    const result = await apiRequest(() =>
      this.client.POST('/api/devices', {
        body: {
          device_model_id: deviceModelId,
          config: JSON.stringify(config),
        },
      })
    );

    const data = result.data!;
    return {
      id: data.id,
      key: data.key,
      deviceModelId: data.device_model_id,
      config: data.config,
      deviceName: data.device_name ?? null,
      deviceEntityId: data.device_entity_id ?? null,
      enableOta: data.enable_ota ?? null,
      rotationState: data.rotation_state,
      clientId: data.client_id,
    };
  }

  /**
   * Delete a device by ID
   */
  async delete(id: number): Promise<void> {
    await apiRequest(() =>
      this.client.DELETE('/api/devices/{device_id}', {
        params: { path: { device_id: id } },
      })
    );
  }

  /**
   * Get a device by ID
   */
  async get(id: number): Promise<CreatedDevice | null> {
    try {
      const { data } = await apiRequest(() =>
        this.client.GET('/api/devices/{device_id}', {
          params: { path: { device_id: id } },
        })
      );
      if (!data) return null;
      return {
        id: data.id,
        key: data.key,
        deviceModelId: data.device_model_id,
        config: data.config,
        deviceName: data.device_name ?? null,
        deviceEntityId: data.device_entity_id ?? null,
        enableOta: data.enable_ota ?? null,
        rotationState: data.rotation_state,
        clientId: data.client_id,
      };
    } catch (error) {
      // Return null for 404
      if (error instanceof Error && error.message.includes('404')) {
        return null;
      }
      throw error;
    }
  }

  /**
   * List all devices
   */
  async list(): Promise<Array<{
    id: number;
    key: string;
    device_model_id: number;
    device_name: string | null;
    device_entity_id: string | null;
    enable_ota: boolean | null;
    rotation_state: string;
  }>> {
    const result = await apiRequest(() =>
      this.client.GET('/api/devices')
    );

    return result.data?.devices || [];
  }

  /**
   * Find a device by key and return its ID
   */
  async findIdByKey(key: string): Promise<number | null> {
    const devices = await this.list();
    const device = devices.find(d => d.key === key);
    return device?.id ?? null;
  }

  /**
   * Delete a device by key (looks up the ID first)
   */
  async deleteByKey(key: string): Promise<void> {
    const id = await this.findIdByKey(key);
    if (id !== null) {
      await this.delete(id);
    }
  }

  /**
   * Create a coredump record for a device via the testing endpoint.
   * Uses POST /api/testing/coredumps to seed coredump data directly in the database.
   */
  async createCoredump(options: CoredumpFactoryOptions): Promise<CreatedCoredump> {
    const result = await apiRequest(() =>
      this.client.POST('/api/testing/coredumps', {
        body: {
          device_id: options.deviceId,
          chip: options.chip ?? 'esp32s3',
          firmware_version: options.firmwareVersion ?? '0.0.0-test',
          size: options.size ?? 262144,
          parse_status: options.parseStatus ?? 'PARSED',
          parsed_output: options.parsedOutput ?? null,
        },
      })
    );

    const data = result.data!;
    return {
      id: data.id,
      deviceId: data.device_id,
      chip: data.chip,
      firmwareVersion: data.firmware_version,
      size: data.size,
      parseStatus: data.parse_status,
      parsedOutput: data.parsed_output ?? null,
      parsedAt: data.parsed_at ?? null,
      uploadedAt: data.uploaded_at,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
    };
  }

  /**
   * Get access to the device models factory for creating models directly
   */
  get deviceModels(): DeviceModelsFactory {
    return this.deviceModelsFactory;
  }
}
