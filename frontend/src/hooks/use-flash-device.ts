/**
 * Hook for flashing an ESP32's full firmware via the Web Serial API.
 *
 * The workflow:
 * 1. Connect to the device via Web Serial and identify its chip
 * 2. Refuse a chip other than the one the build targets, before writing anything
 * 3. Write every image of the build at its offset, no erase-all, so NVS and the
 *    device's provisioning stay as they are; each image is verified against the
 *    flash's own MD5 after it is written
 * 4. Hard-reset the device so it boots the new firmware
 */

/// <reference types="w3c-web-serial" />

import { useState, useCallback, useRef } from 'react';
import {
  ESPLoader,
  Transport,
  chipNameToIdfTarget,
  md5OfBinaryString,
} from '@/lib/esptool';
import type { DeviceFlashImage, DeviceFlashSet } from '@/hooks/use-devices';

type FlashPhase = 'idle' | 'connecting' | 'writing' | 'resetting' | 'success' | 'error';

interface FlashState {
  phase: FlashPhase;
  progress: number;
  message: string;
  error: string | null;
  /** The phase the flash failed in; null unless phase is error */
  failedPhase: FlashPhase | null;
  /** The firmware version being written; null while idle */
  firmwareVersion: string | null;
}

interface UseFlashDeviceResult {
  state: FlashState;
  /** Flash the given images of a firmware version onto a device the user picks */
  startFlash: (flash: DeviceFlashSet, firmwareVersion: string) => Promise<void>;
  /** Abort the current flash and reset state */
  abort: () => Promise<void>;
  /** Reset state to idle */
  reset: () => void;
  isFlashing: boolean;
  isSuccess: boolean;
  isError: boolean;
}

// idf.py flash's default baud rate; the ROM loader always talks at 115200 first
const FLASH_BAUDRATE = 460800;
const ROM_BAUDRATE = 115200;

const initialState: FlashState = {
  phase: 'idle',
  progress: 0,
  message: '',
  error: null,
  failedPhase: null,
  firmwareVersion: null,
};

const terminal = {
  clean: () => {},
  writeLine: (data: string) => {
    if (import.meta.env.DEV) {
      console.log('[ESPLoader]', data);
    }
  },
  write: (data: string) => {
    if (import.meta.env.DEV) {
      console.log('[ESPLoader]', data);
    }
  },
};

/**
 * esptool.py's hard reset: RTS holds EN low, then releases it, and the chip
 * boots from flash. esptool-js 0.5.7's `HardReset` only releases RTS and never
 * asserts it (node_modules/esptool-js/lib/reset.js), which resets nothing.
 */
async function hardReset(transport: Transport): Promise<void> {
  await transport.setRTS(true);
  await new Promise(resolve => setTimeout(resolve, 100));
  await transport.setRTS(false);
}

export function useFlashDevice(): UseFlashDeviceResult {
  const [state, setState] = useState<FlashState>(initialState);

  const portRef = useRef<SerialPort | null>(null);
  const transportRef = useRef<Transport | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  // The current phase, for the error handler's closure
  const phaseRef = useRef<FlashPhase>('idle');

  const updateState = useCallback((updates: Partial<FlashState>) => {
    if (updates.phase) {
      phaseRef.current = updates.phase;
    }
    setState(prev => ({ ...prev, ...updates }));
  }, []);

  /**
   * Close the serial connection. A device on its USB-Serial-JTAG port
   * re-enumerates when it resets, so its port can be gone by now and closing
   * it fails; there is nothing left to close then.
   */
  const releasePort = useCallback(async () => {
    const transport = transportRef.current;
    const port = portRef.current;
    transportRef.current = null;
    portRef.current = null;
    abortControllerRef.current = null;

    try {
      if (transport) {
        // Closes the port too
        await transport.disconnect();
      } else if (port) {
        await port.close();
      }
    } catch {
      // The port is gone
    }
  }, []);

  const reset = useCallback(() => {
    phaseRef.current = 'idle';
    setState(initialState);
  }, []);

  const abort = useCallback(async () => {
    abortControllerRef.current?.abort();
    await releasePort();
    reset();
  }, [releasePort, reset]);

  const startFlash = useCallback(
    async (flash: DeviceFlashSet, firmwareVersion: string) => {
      const controller = new AbortController();
      abortControllerRef.current = controller;
      const { signal } = controller;
      // The image being written, to name it when its write or verification fails
      const writing: { image: DeviceFlashImage | null } = { image: null };

      try {
        // Phase 1: connect and identify the chip
        updateState({
          ...initialState,
          phase: 'connecting',
          progress: 2,
          message: 'Select your ESP32 device...',
          firmwareVersion,
        });

        let port: SerialPort;
        try {
          port = await navigator.serial.requestPort();
        } catch (err) {
          // The user closed the port picker without choosing a port
          if (err instanceof Error && err.name === 'NotFoundError') {
            abortControllerRef.current = null;
            reset();
            return;
          }
          throw err;
        }
        if (signal.aborted) return;
        portRef.current = port;

        updateState({ progress: 5, message: 'Connecting to device...' });

        const transport = new Transport(port);
        transportRef.current = transport;
        const loader = new ESPLoader({
          transport,
          baudrate: FLASH_BAUDRATE,
          romBaudrate: ROM_BAUDRATE,
          terminal,
        });
        await loader.main();
        if (signal.aborted) return;

        // Phase 2: nothing is written to a chip the build does not target
        const chipName = loader.chip.CHIP_NAME;
        if (chipNameToIdfTarget(chipName) !== flash.chip) {
          throw new Error(
            `The connected chip is an ${chipName}, but firmware ${firmwareVersion} is built for ${flash.chip}. Nothing was written.`
          );
        }

        // Phase 3: write and verify every image
        updateState({
          phase: 'writing',
          progress: 10,
          message: `Connected to ${chipName}. Writing firmware ${firmwareVersion}...`,
        });

        const totalBytes = flash.images.reduce((sum, image) => sum + image.size, 0);
        const bytesBefore = flash.images.map((_, index) =>
          flash.images.slice(0, index).reduce((sum, image) => sum + image.size, 0)
        );

        await loader.writeFlash({
          fileArray: flash.images.map(image => ({
            data: atob(image.data),
            address: image.offset,
          })),
          // The build wrote its flash settings into its bootloader's header,
          // so each image is written as the build made it
          flashSize: 'keep',
          flashMode: 'keep',
          flashFreq: 'keep',
          eraseAll: false,
          compress: true,
          // esptool-js compares each written image with the MD5 the chip
          // computes over the flash only when given this
          calculateMD5Hash: md5OfBinaryString,
          reportProgress: (fileIndex, written, total) => {
            const image = flash.images[fileIndex];
            writing.image = image;
            const bytesDone = bytesBefore[fileIndex] + image.size * (written / total);
            updateState({
              progress: 10 + Math.floor((bytesDone / totalBytes) * 85),
              message: `Writing ${image.file} at 0x${image.offset.toString(16)}... ${Math.floor((written / total) * 100)}%`,
            });
          },
        });
        if (signal.aborted) return;

        // Phase 4: boot the new firmware
        updateState({ phase: 'resetting', progress: 97, message: 'Resetting the device...' });
        await hardReset(transport);
        await releasePort();

        updateState({
          phase: 'success',
          progress: 100,
          message: `Firmware ${firmwareVersion} written and verified. The device has been reset.`,
        });
      } catch (err) {
        // An abort has already released the port and reset the state
        if (signal.aborted) return;

        const failedPhase = phaseRef.current;
        const message = err instanceof Error ? err.message : String(err);
        await releasePort();
        updateState({
          phase: 'error',
          error: failedPhase === 'writing' && writing.image
            ? `${writing.image.file} at 0x${writing.image.offset.toString(16)}: ${message}`
            : message,
          failedPhase,
          message: 'Flash failed',
        });
      }
    },
    [updateState, releasePort, reset]
  );

  return {
    state,
    startFlash,
    abort,
    reset,
    isFlashing: state.phase === 'connecting' || state.phase === 'writing' || state.phase === 'resetting',
    isSuccess: state.phase === 'success',
    isError: state.phase === 'error',
  };
}
