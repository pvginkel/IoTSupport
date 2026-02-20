/**
 * Modal component for ESP32 device provisioning workflow.
 *
 * This modal manages the user-facing provisioning flow:
 * - Shows instructions before starting
 * - Displays progress during provisioning
 * - Shows success message with reset instruction
 * - Handles errors with retry option
 * - Confirms close during active operation
 */

import { useState, useCallback } from 'react';
import { Cpu, CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';
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
import { useProvisioning } from '@/hooks/use-provisioning';
import { isWebSerialSupported } from '@/lib/esptool';

interface ProvisionDeviceModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal open state changes */
  onOpenChange: (open: boolean) => void;
  /** Device ID for provisioning */
  deviceId: number;
  /** Device key for display */
  deviceKey: string;
}

/**
 * Progress bar component with animation
 */
function ProgressBar({ progress }: { progress: number }) {
  return (
    <div
      className="w-full h-2 bg-muted rounded-full overflow-hidden"
      data-testid="devices.provision-modal.progress-bar"
    >
      <div
        className="h-full bg-primary transition-all duration-300 ease-out"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}

/**
 * Phase indicator showing current step in workflow
 */
function PhaseIndicator({ phase, message }: { phase: string; message: string }) {
  const getPhaseIcon = () => {
    switch (phase) {
      case 'success':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'error':
        return <XCircle className="h-5 w-5 text-red-500" />;
      default:
        return (
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        );
    }
  };

  return (
    <div className="flex items-center gap-3">
      {getPhaseIcon()}
      <span
        className="text-sm text-muted-foreground"
        data-testid="devices.provision-modal.status-message"
      >
        {message}
      </span>
    </div>
  );
}

export function ProvisionDeviceModal({
  open,
  onOpenChange,
  deviceId,
  deviceKey,
}: ProvisionDeviceModalProps) {
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  const {
    state,
    startProvisioning,
    abort,
    reset,
    isProvisioning,
    isSuccess,
    isError,
  } = useProvisioning(deviceId);

  const webSerialSupported = isWebSerialSupported();

  /**
   * Handle modal close request
   */
  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (!newOpen && isProvisioning) {
        // Show confirmation when closing during active operation
        setShowCloseConfirm(true);
        return;
      }

      if (!newOpen) {
        // Reset state when closing
        reset();
      }

      onOpenChange(newOpen);
    },
    [isProvisioning, onOpenChange, reset]
  );

  /**
   * Confirm close during operation
   */
  const handleConfirmClose = useCallback(() => {
    setShowCloseConfirm(false);
    abort();
    onOpenChange(false);
  }, [abort, onOpenChange]);


  /**
   * Handle connect button click
   */
  const handleConnect = useCallback(() => {
    void startProvisioning();
  }, [startProvisioning]);

  /**
   * Handle retry button click
   */
  const handleRetry = useCallback(() => {
    reset();
    void startProvisioning();
  }, [reset, startProvisioning]);

  /**
   * Render idle state - initial prompt
   */
  const renderIdleState = () => {
    if (!webSerialSupported) {
      return (
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-4 bg-red-900/20 border border-red-800 rounded-lg">
            <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <p
                className="text-red-400 font-medium"
                data-testid="devices.provision-modal.unsupported-error"
              >
                Web Serial API not supported
              </p>
              <p className="text-sm text-red-400/80 mt-1">
                Web Serial API is not supported in this browser. Please use Chrome, Edge, or Opera on desktop.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => handleOpenChange(false)}
              data-testid="devices.provision-modal.close-button"
            >
              Close
            </Button>
          </DialogFooter>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <div className="flex items-start gap-3 p-4 bg-secondary/50 border border-border rounded-lg">
          <Cpu className="h-5 w-5 text-primary shrink-0 mt-0.5" />
          <div className="text-sm text-muted-foreground space-y-2">
            <p>To provision this device:</p>
            <ol className="list-decimal list-inside space-y-1 text-muted-foreground/80">
              <li>Connect your ESP32 device via USB</li>
              <li>Click "Connect" and select the device from the browser popup</li>
              <li>Wait for the credentials to be written to the device</li>
              <li>Reset the device manually when complete</li>
            </ol>
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
            data-testid="devices.provision-modal.close-button"
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleConnect}
            data-testid="devices.provision-modal.connect-button"
          >
            Connect
          </Button>
        </DialogFooter>
      </div>
    );
  };

  /**
   * Render active provisioning state
   */
  const renderProvisioningState = () => (
    <div className="space-y-6">
      <div className="space-y-4">
        <ProgressBar progress={state.progress} />
        <PhaseIndicator phase={state.phase} message={state.message} />
      </div>
      <DialogFooter>
        <Button
          variant="outline"
          onClick={() => handleOpenChange(false)}
          data-testid="devices.provision-modal.close-button"
        >
          Cancel
        </Button>
      </DialogFooter>
    </div>
  );

  /**
   * Render success state
   */
  const renderSuccessState = () => (
    <div className="space-y-4">
      <div className="flex items-start gap-3 p-4 bg-green-900/20 border border-green-800 rounded-lg">
        <CheckCircle className="h-5 w-5 text-green-400 shrink-0 mt-0.5" />
        <div>
          <p
            className="text-green-400 font-medium"
            data-testid="devices.provision-modal.success-message"
          >
            Provisioning Complete
          </p>
          <p className="text-sm text-green-400/80 mt-1">
            Device credentials have been written successfully. Please reset the device manually
            to apply the new configuration.
          </p>
        </div>
      </div>
      <DialogFooter>
        <Button
          variant="primary"
          onClick={() => handleOpenChange(false)}
          data-testid="devices.provision-modal.close-button"
        >
          Done
        </Button>
      </DialogFooter>
    </div>
  );

  /**
   * Render error state
   */
  const renderErrorState = () => (
    <div className="space-y-4">
      <div className="flex items-start gap-3 p-4 bg-red-900/20 border border-red-800 rounded-lg">
        <XCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-red-400 font-medium">Provisioning Failed</p>
          <p
            className="text-sm text-red-400/80 mt-1 font-mono break-all"
            data-testid="devices.provision-modal.error-message"
          >
            {state.error}
          </p>
        </div>
      </div>
      <DialogFooter>
        <Button
          variant="outline"
          onClick={() => handleOpenChange(false)}
          data-testid="devices.provision-modal.close-button"
        >
          Close
        </Button>
        <Button
          variant="primary"
          onClick={handleRetry}
          data-testid="devices.provision-modal.retry-button"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      </DialogFooter>
    </div>
  );

  /**
   * Render appropriate content based on current state
   */
  const renderContent = () => {
    if (isSuccess) {
      return renderSuccessState();
    }

    if (isError) {
      return renderErrorState();
    }

    if (isProvisioning) {
      return renderProvisioningState();
    }

    return renderIdleState();
  };

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={handleOpenChange}
        contentProps={{ 'data-testid': 'devices.provision-modal' }}
      >
        <DialogInnerContent>
          <DialogHeader>
            <DialogTitle>Provision Device</DialogTitle>
            <DialogDescription>
              Flash credentials to device: {deviceKey}
            </DialogDescription>
          </DialogHeader>
          {renderContent()}
        </DialogInnerContent>
      </Dialog>

      {/* Confirmation dialog for closing during operation */}
      <ConfirmDialog
        open={showCloseConfirm}
        onOpenChange={setShowCloseConfirm}
        onConfirm={handleConfirmClose}
        title="Cancel Provisioning?"
        description="Closing now may leave the device in an inconsistent state. Are you sure you want to cancel?"
        confirmText="Yes, Cancel"
        cancelText="Continue"
        destructive
        contentProps={{ 'data-testid': 'devices.provision-modal.close-confirm-dialog' }}
      />
    </>
  );
}
