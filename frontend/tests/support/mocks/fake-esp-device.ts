import type { Page } from '@playwright/test';
import type { ESPLoaderMockConfig, FakeEspDeviceState } from './esptool-mock';

/**
 * Install the fake ESP32 a spec connects to over USB, before the page loads.
 *
 * Playwright cannot drive the browser's Web Serial port picker, so
 * `navigator.serial.requestPort()` hands out a fake port instead, one that
 * records the signals set on it. The esptool-js mock plays the port's chip,
 * configured by `chip`. Both record into `window.__fakeEspDevice`, which
 * `readFakeEspDevice()` reads back. Nothing else is faked: every request still
 * goes to the real backend.
 */
export async function installFakeEspDevice(
  page: Page,
  chip: Partial<ESPLoaderMockConfig> = {}
): Promise<void> {
  await page.addInitScript((chipConfig: Partial<ESPLoaderMockConfig>) => {
    const state: FakeEspDeviceState = { chip: chipConfig, portRequests: 0, operations: [] };
    window.__fakeEspDevice = state;

    const port = {
      // Espressif's USB-Serial-JTAG, the ESP32-S3's own USB port
      getInfo: () => ({ usbVendorId: 0x303a, usbProductId: 0x1001 }),
      open: async () => {},
      close: async () => {},
      setSignals: async (signals: SerialOutputSignals) => {
        state.operations.push({ op: 'signals', signals });
      },
    };

    Object.defineProperty(navigator, 'serial', {
      configurable: true,
      value: {
        requestPort: async () => {
          state.portRequests += 1;
          return port;
        },
        getPorts: async () => [port],
      },
    });
  }, chip);
}

/** What the fake device was asked for and made to do so far. */
export async function readFakeEspDevice(page: Page): Promise<FakeEspDeviceState> {
  return page.evaluate(() => {
    const state = window.__fakeEspDevice;
    if (!state) {
      throw new Error('The fake ESP device is not installed: call installFakeEspDevice() before the page loads');
    }
    return state;
  });
}
