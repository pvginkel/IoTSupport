import { ulid } from 'ulid';
import type { Page } from '@playwright/test';

export interface DeviceFactoryOptions {
  macAddress?: string;
  deviceName?: string;
  deviceEntityId?: string;
  enableOTA?: boolean;
}

export class DevicesFactory {
  constructor(
    private baseUrl: string,
    private page: Page
  ) {}

  /**
   * Generate a random MAC address for testing
   * Format: XX-XX-XX-XX-XX-XX (6 pairs of hex digits with hyphen separators)
   */
  randomMacAddress(): string {
    const id = ulid().slice(0, 12).toUpperCase();
    return `${id.slice(0, 2)}-${id.slice(2, 4)}-${id.slice(4, 6)}-${id.slice(6, 8)}-${id.slice(8, 10)}-${id.slice(10, 12)}`;
  }

  /**
   * Create a device configuration
   * Note: Backend normalizes MAC addresses to lowercase
   */
  async create(options: DeviceFactoryOptions = {}): Promise<{
    macAddress: string;
    config: Record<string, unknown>;
  }> {
    const inputMac = options.macAddress || this.randomMacAddress();
    // Backend normalizes to lowercase
    const macAddress = inputMac.toLowerCase();
    const config = {
      deviceName: options.deviceName || `Test Device ${ulid()}`,
      deviceEntityId: options.deviceEntityId || `test_device_${ulid()}`,
      enableOTA: options.enableOTA ?? false,
    };

    const response = await this.page.request.put(
      `${this.baseUrl}/api/configs/${encodeURIComponent(macAddress)}`,
      {
        data: { content: config, allow_overwrite: true },
      }
    );

    if (!response.ok()) {
      const text = await response.text();
      throw new Error(`Failed to create device: ${response.status()} ${response.statusText()} - ${text}`);
    }

    return { macAddress, config };
  }

  /**
   * Delete a device configuration
   */
  async delete(macAddress: string): Promise<void> {
    const response = await this.page.request.delete(
      `${this.baseUrl}/api/configs/${encodeURIComponent(macAddress)}`
    );

    if (!response.ok()) {
      const text = await response.text();
      throw new Error(`Failed to delete device: ${response.status()} ${response.statusText()} - ${text}`);
    }
  }

  /**
   * Get a device configuration
   */
  async get(macAddress: string): Promise<Record<string, unknown> | null> {
    const response = await this.page.request.get(
      `${this.baseUrl}/api/configs/${encodeURIComponent(macAddress)}`
    );

    if (!response.ok()) {
      if (response.status() === 404) {
        return null;
      }
      const text = await response.text();
      throw new Error(`Failed to get device: ${response.status()} ${response.statusText()} - ${text}`);
    }

    const data = await response.json();
    return data?.content || null;
  }

  /**
   * List all device configurations
   */
  async list(): Promise<Array<{
    mac_address: string;
    device_name: string | null;
    device_entity_id: string | null;
    enable_ota: boolean | null;
  }>> {
    const response = await this.page.request.get(`${this.baseUrl}/api/configs`);

    if (!response.ok()) {
      const text = await response.text();
      throw new Error(`Failed to list devices: ${response.status()} ${response.statusText()} - ${text}`);
    }

    const data = await response.json();
    return data?.configs || [];
  }
}
