import { ulid } from 'ulid';
import type { Page } from '@playwright/test';
import { createApiClient, createPlaywrightFetch, apiRequest, type ApiClient } from '../client';

export interface DeviceModelFactoryOptions {
  code?: string;
  name?: string;
  configSchema?: Record<string, unknown> | null;
}

export interface CreatedDeviceModel {
  id: number;
  code: string;
  name: string;
  hasConfigSchema: boolean;
  configSchema: Record<string, unknown> | null;
  deviceCount: number;
  firmwareVersion: string | null;
  createdAt: string;
  updatedAt: string;
}

export class DeviceModelsFactory {
  private client: ApiClient;

  constructor(baseUrl: string, page: Page) {
    // Use Playwright's request context for cookie sharing with the browser
    this.client = createApiClient({
      baseUrl,
      fetch: createPlaywrightFetch(page.request),
    });
  }

  /**
   * Generate a random model code for testing
   * Format: lowercase alphanumeric with underscores (e.g., "sensor_abc123def456")
   * Uses 16 characters from ULID to include both timestamp and random parts,
   * ensuring uniqueness across parallel test workers.
   */
  randomModelCode(prefix = 'model'): string {
    const suffix = ulid().toLowerCase().slice(0, 16);
    return `${prefix}_${suffix}`;
  }

  /**
   * Generate a random model name for testing
   * Format: Human-readable name (e.g., "Test Model ABC123DEF456")
   * Uses 12 characters from ULID to include randomness for parallel test isolation.
   */
  randomModelName(prefix = 'Test Model'): string {
    const suffix = ulid().slice(0, 12);
    return `${prefix} ${suffix}`;
  }

  /**
   * Create a device model
   */
  async create(options: DeviceModelFactoryOptions = {}): Promise<CreatedDeviceModel> {
    const code = options.code || this.randomModelCode();
    const name = options.name || this.randomModelName();
    const configSchema = options.configSchema ?? null;

    const result = await apiRequest(() =>
      this.client.POST('/api/device-models', {
        body: {
          code,
          name,
          config_schema: configSchema ? JSON.stringify(configSchema) : null,
        },
      })
    );

    const data = result.data!;
    return {
      id: data.id,
      code: data.code,
      name: data.name,
      hasConfigSchema: data.has_config_schema,
      configSchema: data.config_schema ?? null,
      deviceCount: data.device_count,
      firmwareVersion: data.firmware_version ?? null,
      createdAt: data.created_at,
      updatedAt: data.updated_at,
    };
  }

  /**
   * Delete a device model by ID
   */
  async delete(id: number): Promise<void> {
    await apiRequest(() =>
      this.client.DELETE('/api/device-models/{model_id}', {
        params: { path: { model_id: id } },
      })
    );
  }

  /**
   * Get a device model by ID
   */
  async get(id: number): Promise<CreatedDeviceModel | null> {
    try {
      const { data } = await apiRequest(() =>
        this.client.GET('/api/device-models/{model_id}', {
          params: { path: { model_id: id } },
        })
      );
      if (!data) return null;
      return {
        id: data.id,
        code: data.code,
        name: data.name,
        hasConfigSchema: data.has_config_schema,
        configSchema: data.config_schema ?? null,
        deviceCount: data.device_count,
        firmwareVersion: data.firmware_version ?? null,
        createdAt: data.created_at,
        updatedAt: data.updated_at,
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
   * List all device models
   */
  async list(): Promise<Array<{
    id: number;
    code: string;
    name: string;
    has_config_schema: boolean;
    device_count: number;
    firmware_version: string | null;
  }>> {
    const result = await apiRequest(() =>
      this.client.GET('/api/device-models')
    );

    return result.data?.device_models || [];
  }

  /**
   * Find a device model by code
   */
  async findByCode(code: string): Promise<number | null> {
    const models = await this.list();
    const model = models.find(m => m.code === code);
    return model?.id ?? null;
  }
}
