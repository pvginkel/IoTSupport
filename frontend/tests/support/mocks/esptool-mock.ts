/**
 * Mock implementation of esptool-js for Playwright tests.
 *
 * This mock allows testing the provisioning workflow without actual hardware
 * by simulating the ESPLoader and Transport classes with configurable behaviors.
 *
 * The mock is enabled via Vite's resolve.alias when VITE_TEST_MODE=true.
 */

/// <reference types="w3c-web-serial" />

/**
 * LoaderOptions for ESPLoader constructor
 */
export interface LoaderOptions {
  transport: Transport;
  baudrate: number;
  romBaudrate: number;
  terminal?: {
    clean?: () => void;
    writeLine?: (data: string) => void;
    write?: (data: string) => void;
  };
}

/**
 * FlashOptions for writeFlash method
 */
export interface FlashOptions {
  fileArray: Array<{ data: string; address: number }>;
  flashSize: string;
  flashMode: string;
  flashFreq: string;
  eraseAll: boolean;
  compress: boolean;
  reportProgress?: (fileIndex: number, written: number, total: number) => void;
  calculateMD5Hash?: (image: string) => string;
}

/**
 * Terminal interface for ESPLoader output
 */
export interface IEspLoaderTerminal {
  clean?: () => void;
  writeLine?: (data: string) => void;
  write?: (data: string) => void;
}

/**
 * Partition table entry as parsed from ESP32 devices
 */
export interface PartitionInfo {
  name: string;
  type: number;
  subtype: number;
  offset: number;
  size: number;
}

/**
 * Configuration for mock behavior
 */
export interface ESPLoaderMockConfig {
  /** Result of connection attempt */
  connectionResult: 'success' | 'timeout' | 'error';
  /** Simulated partition table (null = read failure) */
  partitionTable: PartitionInfo[] | null;
  /** Result of flash write operation */
  flashWriteResult: 'success' | 'error';
  /** Result of MD5 verification */
  verificationResult: 'match' | 'mismatch';
  /** Simulated chip name */
  chipName: string;
  /** Delay in ms for operations (for testing progress updates) */
  operationDelayMs: number;
}

// Default configuration
const defaultConfig: ESPLoaderMockConfig = {
  connectionResult: 'success',
  partitionTable: [
    { name: 'nvs', type: 1, subtype: 2, offset: 0x9000, size: 0x5000 },
    { name: 'otadata', type: 1, subtype: 0, offset: 0xe000, size: 0x2000 },
    { name: 'app', type: 0, subtype: 0, offset: 0x10000, size: 0x100000 },
  ],
  flashWriteResult: 'success',
  verificationResult: 'match',
  chipName: 'ESP32',
  operationDelayMs: 50,
};

// Current mock configuration (can be changed via configureESPLoaderMock)
let currentConfig: ESPLoaderMockConfig = { ...defaultConfig };

/**
 * Configure the ESPLoader mock behavior for tests.
 * Call this before running provisioning operations to set up expected outcomes.
 */
export function configureESPLoaderMock(config: Partial<ESPLoaderMockConfig>): void {
  currentConfig = { ...currentConfig, ...config };
}

/**
 * Reset the ESPLoader mock to default configuration.
 */
export function resetESPLoaderMock(): void {
  currentConfig = { ...defaultConfig };
}

/**
 * Get current mock configuration (for debugging)
 */
export function getESPLoaderMockConfig(): ESPLoaderMockConfig {
  return { ...currentConfig };
}

// Track expected MD5 for verification
let expectedMd5: string = '';
let writtenData: Uint8Array | null = null;
let lastWriteAddress: number = 0;

/**
 * Mock Transport class wrapping a SerialPort
 */
export class Transport {
  device: SerialPort;
  tracing: boolean;
  slipReaderEnabled: boolean;
  baudrate: number;

  constructor(device: SerialPort, tracing = false, enableSlipReader = true) {
    this.device = device;
    this.tracing = tracing;
    this.slipReaderEnabled = enableSlipReader;
    this.baudrate = 115200;
  }

  getInfo(): string {
    return 'Mock ESP32 Device (VID: 0x10C4, PID: 0xEA60)';
  }

  getPid(): number | undefined {
    return 0xEA60;
  }

  async connect(baud = 115200): Promise<void> {
    this.baudrate = baud;
    await this.sleep(currentConfig.operationDelayMs);
  }

  async disconnect(): Promise<void> {
    await this.sleep(10);
  }

  async setRTS(state: boolean): Promise<void> {
    void state;
    await this.sleep(10);
  }

  async setDTR(state: boolean): Promise<void> {
    void state;
    await this.sleep(10);
  }

  sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async waitForUnlock(timeout: number): Promise<void> {
    void timeout;
    await this.sleep(10);
  }
}

/**
 * Simulated ROM class for chip identification
 */
class MockROM {
  CHIP_NAME = currentConfig.chipName;
  FLASH_WRITE_SIZE = 0x400;
  TEXT_START = 0x40000000;
}

/**
 * Mock ESPLoader class for testing provisioning workflow
 */
export class ESPLoader {
  // Constants from real ESPLoader
  ESP_RAM_BLOCK = 0x1800;
  ESP_FLASH_BEGIN = 0x02;
  ESP_FLASH_DATA = 0x03;
  ESP_FLASH_END = 0x04;
  ESP_MEM_BEGIN = 0x05;
  ESP_MEM_END = 0x06;
  ESP_MEM_DATA = 0x07;
  ESP_WRITE_REG = 0x09;
  ESP_READ_REG = 0x0a;
  ESP_SPI_ATTACH = 0x0d;
  ESP_CHANGE_BAUDRATE = 0x0f;
  ESP_FLASH_DEFL_BEGIN = 0x10;
  ESP_FLASH_DEFL_DATA = 0x11;
  ESP_FLASH_DEFL_END = 0x12;
  ESP_SPI_FLASH_MD5 = 0x13;
  ESP_ERASE_FLASH = 0xd0;
  ESP_ERASE_REGION = 0xd1;
  ESP_READ_FLASH = 0xd2;
  ESP_RUN_USER_CODE = 0xd3;

  DEFAULT_TIMEOUT = 3000;
  CHIP_ERASE_TIMEOUT = 120000;
  FLASH_READ_TIMEOUT = 100000;
  MAX_TIMEOUT = 240000;

  chip: MockROM;
  IS_STUB = false;
  FLASH_WRITE_SIZE = 0x400;
  transport: Transport;

  private terminal?: IEspLoaderTerminal;

  constructor(options: LoaderOptions) {
    this.transport = options.transport;
    this.terminal = options.terminal;
    this.chip = new MockROM();
  }

  write(str: string, withNewline = true): void {
    if (this.terminal?.write) {
      this.terminal.write(withNewline ? str + '\n' : str);
    }
  }

  info(str: string, withNewline = true): void {
    this.write(str, withNewline);
  }

  error(str: string, withNewline = true): void {
    this.write('ERROR: ' + str, withNewline);
  }

  debug(str: string, withNewline = true): void {
    this.write('DEBUG: ' + str, withNewline);
  }

  private async sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Simulate connection to ESP32 device
   */
  async connect(mode = 'default_reset', attempts = 7, detecting = false): Promise<void> {
    void mode;
    void attempts;
    void detecting;

    await this.sleep(currentConfig.operationDelayMs);

    if (currentConfig.connectionResult === 'timeout') {
      throw new Error('Connection timed out: Failed to connect to ESP32 after 7 attempts');
    }

    if (currentConfig.connectionResult === 'error') {
      throw new Error('Serial connection error: Device not responding');
    }

    this.info(`Connected to ${currentConfig.chipName}`);
  }

  /**
   * Detect chip type
   */
  async detectChip(mode = 'default_reset'): Promise<void> {
    void mode;
    await this.sleep(currentConfig.operationDelayMs);
    this.chip = new MockROM();
    this.info(`Chip is ${currentConfig.chipName}`);
  }

  /**
   * Run the flasher stub
   */
  async runStub(): Promise<MockROM> {
    await this.sleep(currentConfig.operationDelayMs);
    this.IS_STUB = true;
    this.info('Stub loaded');
    return this.chip;
  }

  /**
   * Main initialization (connect, detect chip, run stub)
   */
  async main(mode = 'default_reset'): Promise<string> {
    await this.connect(mode);
    await this.detectChip(mode);
    await this.runStub();
    return currentConfig.chipName;
  }

  /**
   * Read flash memory - used to read partition table
   */
  async readFlash(
    addr: number,
    size: number,
    onPacketReceived?: ((packet: Uint8Array, progress: number, totalSize: number) => void) | null
  ): Promise<Uint8Array> {
    await this.sleep(currentConfig.operationDelayMs);

    // Check if reading partition table (address 0x8000)
    if (addr === 0x8000 && currentConfig.partitionTable === null) {
      throw new Error('Failed to read flash at 0x8000: Timeout');
    }

    // Simulate partition table data at 0x8000
    if (addr === 0x8000 && currentConfig.partitionTable) {
      const data = this.buildPartitionTableBinary(currentConfig.partitionTable);

      if (onPacketReceived) {
        // Simulate chunked reading
        const chunkSize = 256;
        for (let offset = 0; offset < size; offset += chunkSize) {
          const progress = Math.min(offset + chunkSize, size);
          onPacketReceived(
            data.slice(offset, offset + chunkSize),
            progress,
            size
          );
          await this.sleep(10);
        }
      }

      // Pad to requested size
      const result = new Uint8Array(size);
      result.set(data.slice(0, Math.min(data.length, size)));
      return result;
    }

    // For other addresses (e.g., verification read-back), return written data if available
    if (writtenData && addr === lastWriteAddress) {
      if (currentConfig.verificationResult === 'mismatch') {
        // Return corrupted data for verification failure
        const corrupted = new Uint8Array(writtenData);
        corrupted[0] = corrupted[0] ^ 0xFF;
        return corrupted;
      }
      return writtenData;
    }

    // Return zeros for other reads
    return new Uint8Array(size);
  }

  /**
   * Build binary partition table from partition info array
   */
  private buildPartitionTableBinary(partitions: PartitionInfo[]): Uint8Array {
    // ESP32 partition table format:
    // Each entry is 32 bytes
    // Magic: 0xAA 0x50
    // Type: 1 byte
    // Subtype: 1 byte
    // Offset: 4 bytes (little-endian)
    // Size: 4 bytes (little-endian)
    // Name: 16 bytes (null-terminated)
    // Flags: 4 bytes

    const entries: Uint8Array[] = [];

    for (const partition of partitions) {
      const entry = new Uint8Array(32);

      // Magic bytes
      entry[0] = 0xAA;
      entry[1] = 0x50;

      // Type and subtype
      entry[2] = partition.type;
      entry[3] = partition.subtype;

      // Offset (little-endian)
      entry[4] = partition.offset & 0xFF;
      entry[5] = (partition.offset >> 8) & 0xFF;
      entry[6] = (partition.offset >> 16) & 0xFF;
      entry[7] = (partition.offset >> 24) & 0xFF;

      // Size (little-endian)
      entry[8] = partition.size & 0xFF;
      entry[9] = (partition.size >> 8) & 0xFF;
      entry[10] = (partition.size >> 16) & 0xFF;
      entry[11] = (partition.size >> 24) & 0xFF;

      // Name (16 bytes, null-terminated)
      const nameBytes = new TextEncoder().encode(partition.name);
      for (let i = 0; i < Math.min(nameBytes.length, 15); i++) {
        entry[12 + i] = nameBytes[i];
      }

      // Flags (4 bytes, all zeros)
      // entry[28-31] already 0

      entries.push(entry);
    }

    // End marker: 32 bytes of 0xFF
    const endMarker = new Uint8Array(32).fill(0xFF);
    entries.push(endMarker);

    // Combine all entries
    const totalLength = entries.reduce((sum, e) => sum + e.length, 0);
    const result = new Uint8Array(totalLength);
    let offset = 0;
    for (const entry of entries) {
      result.set(entry, offset);
      offset += entry.length;
    }

    return result;
  }

  /**
   * Calculate MD5 of flash region
   */
  async flashMd5sum(addr: number, size: number): Promise<string> {
    void addr;
    void size;
    await this.sleep(currentConfig.operationDelayMs);

    if (currentConfig.verificationResult === 'mismatch') {
      return 'ffffffffffffffffffffffffffffffff';
    }

    return expectedMd5 || 'd41d8cd98f00b204e9800998ecf8427e';
  }

  /**
   * Write data to flash
   */
  async writeFlash(options: FlashOptions): Promise<void> {
    if (currentConfig.flashWriteResult === 'error') {
      throw new Error('Flash write error: Failed to write data at specified address');
    }

    for (let fileIndex = 0; fileIndex < options.fileArray.length; fileIndex++) {
      const file = options.fileArray[fileIndex];
      const data = this.bstrToUi8(file.data);
      const total = data.length;

      // Store for verification
      writtenData = data;
      lastWriteAddress = file.address;

      // Calculate expected MD5 if calculator provided
      if (options.calculateMD5Hash) {
        expectedMd5 = options.calculateMD5Hash(file.data);
      }

      // Simulate progress
      const chunkSize = 4096;
      for (let written = 0; written < total; written += chunkSize) {
        await this.sleep(10);
        if (options.reportProgress) {
          options.reportProgress(fileIndex, Math.min(written + chunkSize, total), total);
        }
      }
    }

    this.info('Flash write complete');
  }

  /**
   * Convert byte string to Uint8Array
   */
  bstrToUi8(bStr: string): Uint8Array {
    const arr = new Uint8Array(bStr.length);
    for (let i = 0; i < bStr.length; i++) {
      arr[i] = bStr.charCodeAt(i);
    }
    return arr;
  }

  /**
   * Convert Uint8Array to hex string
   */
  toHex(buffer: number | Uint8Array): string {
    if (typeof buffer === 'number') {
      return buffer.toString(16).padStart(2, '0');
    }
    return Array.from(buffer)
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
  }

  /**
   * Soft reset the device
   */
  async softReset(stayInBootloader: boolean): Promise<void> {
    void stayInBootloader;
    await this.sleep(currentConfig.operationDelayMs);
    this.info('Device reset');
  }

  /**
   * After operation (hard reset, etc.)
   */
  async after(mode = 'hard_reset', usingUsbOtg = false): Promise<void> {
    void mode;
    void usingUsbOtg;
    await this.sleep(currentConfig.operationDelayMs);
  }

  /**
   * Flash size helper
   */
  flashSizeBytes = (flashSize: string): number => {
    const sizes: Record<string, number> = {
      '1MB': 0x100000,
      '2MB': 0x200000,
      '4MB': 0x400000,
      '8MB': 0x800000,
      '16MB': 0x1000000,
    };
    return sizes[flashSize] || 0x400000;
  };

  /**
   * Get flash size
   */
  async getFlashSize(): Promise<number> {
    await this.sleep(currentConfig.operationDelayMs);
    return 0x400000; // 4MB
  }
}

// Re-export reset classes (not used in mock but needed for type compatibility)
export class ClassicReset {
  constructor() {
    // No-op
  }
}

export class HardReset {
  constructor() {
    // No-op
  }
}

export class CustomReset {
  constructor() {
    // No-op
  }
}

export class UsbJtagSerialReset {
  constructor() {
    // No-op
  }
}

export function validateCustomResetStringSequence(): boolean {
  return true;
}

export const ResetConstructors = {
  ClassicReset,
  HardReset,
  CustomReset,
  UsbJtagSerialReset,
};

export class ROM {
  CHIP_NAME = 'ESP32';
}

export function decodeBase64Data(data: string): string {
  return atob(data);
}

export function getStubJsonByChipName(): unknown {
  return {};
}

export type Stub = unknown;
