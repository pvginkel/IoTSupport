/**
 * Modal for flashing a device's full firmware over USB.
 *
 * - Loads what the flash writes when it opens: the device's model's current
 *   firmware version and its images, or why there is nothing to write
 * - Names the firmware version and lists each image with its offset
 * - Shows progress while writing, then the outcome
 * - Confirms close during an active flash
 */

import { useState, useCallback, type ReactNode } from 'react';
import { Zap, CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import {
  Dialog,
  DialogInnerContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog';
import { ConfirmDialog } from '@/components/primitives/dialog';
import { Button } from '@/components/primitives/button';
import { useDeviceFlashImages, type DeviceFlashImages, type DeviceFlashSet } from '@/hooks/use-devices';
import { useFlashDevice } from '@/hooks/use-flash-device';
import { isWebSerialSupported } from '@/lib/esptool';
import { useUiStateInstrumentation } from '@/lib/test/ui-state';
import { flashStatusLabel } from '@/lib/utils/status-labels';
import { formatFileSize } from '@/lib/utils/format';

interface FlashDeviceModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  deviceId: number;
  deviceKey: string;
}

type FlashDevice = ReturnType<typeof useFlashDevice>;

function ProgressBar({ progress }: { progress: number }) {
  return (
    <div
      className="w-full h-2 bg-muted rounded-full overflow-hidden"
      data-testid="devices.flash-modal.progress-bar"
    >
      <div
        className="h-full bg-primary transition-all duration-300 ease-out"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}

function ImageList({ flash }: { flash: DeviceFlashSet }) {
  return (
    <table className="w-full text-sm" data-testid="devices.flash-modal.images">
      <thead>
        <tr className="text-left text-muted-foreground">
          <th className="font-medium pb-1">Offset</th>
          <th className="font-medium pb-1">Image</th>
          <th className="font-medium pb-1 text-right">Size</th>
        </tr>
      </thead>
      <tbody>
        {flash.images.map(image => (
          <tr
            key={image.offset}
            data-testid="devices.flash-modal.image"
            data-offset={image.offset}
          >
            <td className="font-mono py-0.5">0x{image.offset.toString(16)}</td>
            <td className="font-mono py-0.5 break-all">{image.file}</td>
            <td className="py-0.5 text-right">{formatFileSize(image.size)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface FlashDeviceModalContentProps {
  deviceId: number;
  flashDevice: FlashDevice;
  onClose: () => void;
}

/**
 * The modal's body. Mounted only while the modal is open, so each opening
 * fetches the images afresh and closing frees them.
 */
function FlashDeviceModalContent({ deviceId, flashDevice, onClose }: FlashDeviceModalContentProps) {
  const { flashImages, isLoading, error } = useDeviceFlashImages(deviceId);
  const { state, startFlash, reset, isFlashing, isSuccess, isError } = flashDevice;

  // No `error` option, here or for the flash: the hook's unmount cleanup
  // depends on it, so an error set as loading ends would end the scope as
  // 'aborted' with the previous render's metadata (src/lib/test/ui-state.ts)
  useUiStateInstrumentation('devices.flash-modal.images', {
    isLoading,
    getReadyMetadata: () => ({
      flashStatus: flashImages?.status,
      firmwareVersion: flashImages?.firmwareVersion,
      imageCount: flashImages?.status === 'flashable' ? flashImages.flash.images.length : 0,
      error: error instanceof Error ? error.message : null,
    }),
  });

  const closeButton = (label: string): ReactNode => (
    <Button variant="outline" onClick={onClose} data-testid="devices.flash-modal.close-button">
      {label}
    </Button>
  );

  if (isSuccess) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-green-900/20 border border-green-800 rounded-lg">
          <CheckCircle className="h-5 w-5 text-green-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-green-400 font-medium" data-testid="devices.flash-modal.success-message">
              Flash Complete
            </p>
            <p className="text-sm text-green-400/80 mt-1">
              {state.message} Provision the device next if it has no credentials yet.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="primary" onClick={onClose} data-testid="devices.flash-modal.close-button">
            Done
          </Button>
        </DialogFooter>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-red-900/20 border border-red-800 rounded-lg">
          <XCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-red-400 font-medium">Flash Failed</p>
            <p
              className="text-sm text-red-400/80 mt-1 font-mono break-all"
              data-testid="devices.flash-modal.error-message"
            >
              {state.error}
            </p>
          </div>
        </div>
        <DialogFooter>
          {closeButton('Close')}
          {flashImages?.status === 'flashable' && (
            <Button
              variant="primary"
              onClick={() => {
                reset();
                void startFlash(flashImages.flash, flashImages.firmwareVersion);
              }}
              data-testid="devices.flash-modal.retry-button"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Retry
            </Button>
          )}
        </DialogFooter>
      </div>
    );
  }

  if (isFlashing) {
    return (
      <div className="space-y-6">
        <div className="space-y-4">
          <ProgressBar progress={state.progress} />
          <div className="flex items-center gap-3">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-sm text-muted-foreground" data-testid="devices.flash-modal.status-message">
              {state.message}
            </span>
          </div>
        </div>
        <DialogFooter>{closeButton('Cancel')}</DialogFooter>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3" data-testid="devices.flash-modal.loading">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span className="text-sm text-muted-foreground">Loading the device's firmware...</span>
        </div>
        <DialogFooter>{closeButton('Cancel')}</DialogFooter>
      </div>
    );
  }

  if (error || !flashImages) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-red-900/20 border border-red-800 rounded-lg">
          <XCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <p className="text-sm text-red-400" data-testid="devices.flash-modal.load-error">
            Could not load the device's firmware: {error instanceof Error ? error.message : String(error)}
          </p>
        </div>
        <DialogFooter>{closeButton('Close')}</DialogFooter>
      </div>
    );
  }

  return <FlashReadyState flashImages={flashImages} onConnect={startFlash} closeButton={closeButton} />;
}

interface FlashReadyStateProps {
  flashImages: DeviceFlashImages;
  onConnect: (flash: DeviceFlashSet, firmwareVersion: string) => Promise<void>;
  closeButton: (label: string) => ReactNode;
}

/**
 * What the flash would write, before it starts: the firmware and its images,
 * or why there is nothing to write.
 */
function FlashReadyState({ flashImages, onConnect, closeButton }: FlashReadyStateProps) {
  switch (flashImages.status) {
    case 'flashable':
      return (
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-4 bg-secondary/50 border border-border rounded-lg">
            <Zap className="h-5 w-5 text-primary shrink-0 mt-0.5" />
            <div className="text-sm text-muted-foreground space-y-3 min-w-0 flex-1">
              <p>
                Writes firmware{' '}
                <span className="font-mono text-foreground" data-testid="devices.flash-modal.firmware-version">
                  {flashImages.firmwareVersion}
                </span>{' '}
                for the {flashImages.flash.chip}, the version the device's model serves. NVS and the
                device's provisioning are kept.
              </p>
              <ImageList flash={flashImages.flash} />
              <ol className="list-decimal list-inside space-y-1 text-muted-foreground/80">
                <li>Connect your ESP32 device via USB</li>
                <li>Click "Connect" and select the device from the browser popup</li>
                <li>Wait for every image to be written and verified</li>
                <li>The device resets and boots the new firmware</li>
              </ol>
            </div>
          </div>
          <DialogFooter>
            {closeButton('Cancel')}
            <Button
              variant="primary"
              onClick={() => void onConnect(flashImages.flash, flashImages.firmwareVersion)}
              data-testid="devices.flash-modal.connect-button"
            >
              Connect
            </Button>
          </DialogFooter>
        </div>
      );
    case 'no_firmware':
    case 'no_flash_images':
      return (
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-4 bg-amber-900/20 border border-amber-800 rounded-lg">
            <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
            <p
              className="text-sm text-amber-400"
              data-testid="devices.flash-modal.not-flashable"
              data-status={flashImages.status}
            >
              {flashStatusLabel(flashImages)}
            </p>
          </div>
          <DialogFooter>{closeButton('Close')}</DialogFooter>
        </div>
      );
    default: {
      const unknownStatus: never = flashImages;
      throw new Error(`Unknown flash status: ${String(unknownStatus)}`);
    }
  }
}

export function FlashDeviceModal({ open, onOpenChange, deviceId, deviceKey }: FlashDeviceModalProps) {
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);
  const flashDevice = useFlashDevice();
  const { state, abort, reset, isFlashing } = flashDevice;

  useUiStateInstrumentation('devices.flash-modal.flash', {
    isLoading: isFlashing,
    readyOnMount: false,
    getReadyMetadata: () => ({
      outcome: state.phase,
      firmwareVersion: state.firmwareVersion,
      failedPhase: state.failedPhase,
      error: state.error,
    }),
  });

  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (!newOpen && isFlashing) {
        setShowCloseConfirm(true);
        return;
      }
      if (!newOpen) {
        reset();
      }
      onOpenChange(newOpen);
    },
    [isFlashing, onOpenChange, reset]
  );

  const handleConfirmClose = useCallback(() => {
    setShowCloseConfirm(false);
    void abort();
    onOpenChange(false);
  }, [abort, onOpenChange]);

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={handleOpenChange}
        contentProps={{ 'data-testid': 'devices.flash-modal' }}
      >
        <DialogInnerContent>
          <DialogHeader>
            <DialogTitle>Flash Device</DialogTitle>
            <DialogDescription>Write firmware to device: {deviceKey}</DialogDescription>
          </DialogHeader>
          {isWebSerialSupported() ? (
            <FlashDeviceModalContent
              deviceId={deviceId}
              flashDevice={flashDevice}
              onClose={() => handleOpenChange(false)}
            />
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-3 p-4 bg-red-900/20 border border-red-800 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                <p className="text-sm text-red-400" data-testid="devices.flash-modal.unsupported-error">
                  Web Serial API is not supported in this browser. Please use Chrome, Edge, or Opera on desktop.
                </p>
              </div>
              <DialogFooter>
                <Button
                  variant="outline"
                  onClick={() => handleOpenChange(false)}
                  data-testid="devices.flash-modal.close-button"
                >
                  Close
                </Button>
              </DialogFooter>
            </div>
          )}
        </DialogInnerContent>
      </Dialog>

      <ConfirmDialog
        open={showCloseConfirm}
        onOpenChange={setShowCloseConfirm}
        onConfirm={handleConfirmClose}
        title="Cancel Flashing?"
        description="Closing now can leave the device without bootable firmware until it is flashed again. Are you sure you want to cancel?"
        confirmText="Yes, Cancel"
        cancelText="Continue"
        destructive
        contentProps={{ 'data-testid': 'devices.flash-modal.close-confirm-dialog' }}
      />
    </>
  );
}
