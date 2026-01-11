import { ulid } from 'ulid';
import { apiRequest, type ApiClient } from '../client';

export interface DeviceFactoryOptions {
  macAddress?: string;
  deviceName?: string;
  deviceEntityId?: string;
  enableOTA?: boolean;
}

export class DevicesFactory {
  constructor(private client: ApiClient) {}

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

    await apiRequest(() =>
      this.client.PUT('/api/configs/{mac_address}', {
        params: { path: { mac_address: macAddress } },
        body: { content: config, allow_overwrite: true },
      })
    );

    return { macAddress, config };
  }

  /**
   * Delete a device configuration
   */
  async delete(macAddress: string): Promise<void> {
    await apiRequest(() =>
      this.client.DELETE('/api/configs/{mac_address}', {
        params: { path: { mac_address: macAddress } },
      })
    );
  }

  /**
   * Get a device configuration
   */
  async get(macAddress: string): Promise<Record<string, unknown> | null> {
    const result = await apiRequest(() =>
      this.client.GET('/api/configs/{mac_address}', {
        params: { path: { mac_address: macAddress } },
      })
    );

    return result.data?.content || null;
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
    const result = await apiRequest(() =>
      this.client.GET('/api/configs')
    );

    return result.data?.configs || [];
  }
}
