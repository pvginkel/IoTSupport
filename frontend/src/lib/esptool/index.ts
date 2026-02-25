/**
 * ESPTool wrapper module
 *
 * This module provides a unified interface for ESP32 communication.
 * In test mode (VITE_TEST_MODE=true), it uses a mock implementation
 * that doesn't require actual hardware.
 *
 * The mock is configured via Vite's resolve.alias in vite.config.ts.
 */

// Re-export everything from esptool-js
// In test mode, Vite's resolve.alias will redirect this to the mock
export { ESPLoader, Transport } from 'esptool-js';

/**
 * Partition table entry structure as defined in ESP-IDF
 */
export interface PartitionInfo {
  name: string;
  type: number;
  subtype: number;
  offset: number;
  size: number;
}

/**
 * Parse ESP32 partition table binary data.
 *
 * The partition table is stored at 0x8000 in flash and consists of
 * 32-byte entries. Each entry has:
 * - Magic bytes: 0xAA 0x50
 * - Type: 1 byte
 * - Subtype: 1 byte
 * - Offset: 4 bytes (little-endian)
 * - Size: 4 bytes (little-endian)
 * - Name: 16 bytes (null-terminated)
 * - Flags: 4 bytes
 *
 * The table ends with an entry where the first two bytes are 0xFF.
 */
export function parsePartitionTable(data: Uint8Array): PartitionInfo[] {
  const partitions: PartitionInfo[] = [];
  const entrySize = 32;

  for (let offset = 0; offset + entrySize <= data.length; offset += entrySize) {
    const magic1 = data[offset];
    const magic2 = data[offset + 1];

    // Check for end marker (0xFF 0xFF)
    if (magic1 === 0xFF && magic2 === 0xFF) {
      break;
    }

    // Check for valid magic bytes (0xAA 0x50)
    if (magic1 !== 0xAA || magic2 !== 0x50) {
      continue;
    }

    const type = data[offset + 2];
    const subtype = data[offset + 3];

    // Read offset as little-endian 32-bit integer
    const partOffset =
      data[offset + 4] |
      (data[offset + 5] << 8) |
      (data[offset + 6] << 16) |
      (data[offset + 7] << 24);

    // Read size as little-endian 32-bit integer
    const size =
      data[offset + 8] |
      (data[offset + 9] << 8) |
      (data[offset + 10] << 16) |
      (data[offset + 11] << 24);

    // Read name (16 bytes, null-terminated)
    const nameBytes = data.slice(offset + 12, offset + 28);
    const nullIndex = nameBytes.indexOf(0);
    const name = new TextDecoder().decode(
      nullIndex >= 0 ? nameBytes.slice(0, nullIndex) : nameBytes
    );

    partitions.push({
      name,
      type,
      subtype,
      offset: partOffset >>> 0, // Ensure unsigned
      size: size >>> 0,
    });
  }

  return partitions;
}

/**
 * Find the NVS partition in a partition table.
 *
 * NVS partitions have:
 * - type = 1 (data)
 * - subtype = 2 (nvs)
 * - name = "nvs" (convention, but we check subtype for correctness)
 */
export function findNvsPartition(partitions: PartitionInfo[]): PartitionInfo | null {
  // First try to find by name
  const nvsByName = partitions.find(p => p.name === 'nvs');

  if (nvsByName) {
    return nvsByName;
  }

  // Fallback: find by type/subtype
  return partitions.find(p => p.type === 1 && p.subtype === 2) ?? null;
}

/**
 * Decode base64 string to Uint8Array
 */
export function decodeBase64ToUint8Array(base64: string): Uint8Array {
  const binaryString = atob(base64);
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

/**
 * Convert Uint8Array to binary string for ESPLoader
 */
export function uint8ArrayToBinaryString(data: Uint8Array): string {
  let result = '';
  for (let i = 0; i < data.length; i++) {
    result += String.fromCharCode(data[i]);
  }
  return result;
}

/**
 * Check if Web Serial API is available
 */
export function isWebSerialSupported(): boolean {
  return typeof navigator !== 'undefined' &&
    'serial' in navigator &&
    typeof navigator.serial !== 'undefined';
}
