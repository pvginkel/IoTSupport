import { ulid } from 'ulid';
import type { Page } from '@playwright/test';
import { createApiClient, createPlaywrightFetch, apiRequest, type ApiClient } from '../client';

export interface DeviceFactoryOptions {
  macAddress?: string;
  deviceName?: string;
  deviceEntityId?: string;
  enableOTA?: boolean;
}

export interface CreatedDevice {
  id: number;
  macAddress: string;
  config: Record<string, unknown>;
}

export class DevicesFactory {
  private client: ApiClient;

  constructor(baseUrl: string, page: Page) {
    // Use Playwright's request context for cookie sharing with the browser
    this.client = createApiClient({
      baseUrl,
      fetch: createPlaywrightFetch(page.request),
    });
  }

  /**
   * Generate a random MAC address for testing
   * Format: XX:XX:XX:XX:XX:XX (6 pairs of hex digits with colon separators)
   */
  randomMacAddress(): string {
    // Generate 6 random hex bytes
    const bytes = Array.from({ length: 6 }, () =>
      Math.floor(Math.random() * 256).toString(16).padStart(2, '0')
    );
    return bytes.join(':').toLowerCase();
  }

  /**
   * Create a device configuration
   * Note: Backend normalizes MAC addresses to lowercase
   */
  async create(options: DeviceFactoryOptions = {}): Promise<CreatedDevice> {
    const inputMac = options.macAddress || this.randomMacAddress();
    // Backend normalizes to lowercase
    const macAddress = inputMac.toLowerCase();
    const config = {
      deviceName: options.deviceName || `Test Device ${ulid()}`,
      deviceEntityId: options.deviceEntityId || `test_device_${ulid()}`,
      enableOTA: options.enableOTA ?? false,
    };

    const result = await apiRequest(() =>
      this.client.POST('/api/configs', {
        body: {
          mac_address: macAddress,
          content: JSON.stringify(config),
        },
      })
    );

    return {
      id: result.data!.id,
      macAddress: result.data!.mac_address,
      config,
    };
  }

  /**
   * Delete a device configuration by ID
   */
  async delete(id: number): Promise<void> {
    await apiRequest(() =>
      this.client.DELETE('/api/configs/{config_id}', {
        params: { path: { config_id: id } },
      })
    );
  }

  /**
   * Get a device configuration by ID
   */
  async get(id: number): Promise<Record<string, unknown> | null> {
    try {
      const { data } = await apiRequest(() =>
        this.client.GET('/api/configs/{config_id}', {
        params: { path: { config_id: id } },
        })
      );
      return data?.content || null;
    } catch (error) {
      // Return null for 404
      if (error instanceof Error && error.message.includes('404')) {
        return null;
      }
      throw error;
    }
  }

  /**
   * List all device configurations
   */
  async list(): Promise<Array<{
    id: number;
    mac_address: string;
    device_name: string | null;
    device_entity_id: string | null;
    enable_ota: boolean | null;
  }>> {
    const result = await apiRequest(() =>
      this.client.GET('/api/configs')
    );

    return result.data?.configs || [];
  }

  /**
   * Find a device by MAC address and return its ID
   * Useful for cleanup after creating devices via UI
   */
  async findIdByMac(macAddress: string): Promise<number | null> {
    const configs = await this.list();
    // Normalize MAC address for comparison (lowercase)
    const normalizedMac = macAddress.toLowerCase();
    const config = configs.find(c => c.mac_address.toLowerCase() === normalizedMac);
    return config?.id ?? null;
  }

  /**
   * Delete a device by MAC address (looks up the ID first)
   * Useful for cleanup in tests that create devices via UI
   */
  async deleteByMac(macAddress: string): Promise<void> {
    const id = await this.findIdByMac(macAddress);
    if (id !== null) {
      await this.delete(id);
    }
  }
}
