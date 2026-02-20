import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import Editor from '@monaco-editor/react'
import { Cpu } from 'lucide-react'
import { Button } from '@/components/primitives/button'
import { ConfirmDialog } from '@/components/primitives/dialog'
import type { Device } from '@/hooks/use-devices'
import { useDeviceForm } from '@/hooks/use-device-form'
import { KeycloakClientStatus } from './keycloak-client-status'
import { ProvisionDeviceModal } from './provision-device-modal'

interface DeviceConfigurationTabProps {
  device: Device
}

/**
 * Configuration tab content for the device detail view.
 * Handles JSON config editing, Keycloak status, model display,
 * provisioning, and form actions (Save/Cancel/Duplicate).
 */
export function DeviceConfigurationTab({ device }: DeviceConfigurationTabProps) {
  const [provisionModalOpen, setProvisionModalOpen] = useState(false)

  const {
    jsonConfig,
    jsonError,
    isPending,
    isValid,
    monacoEditorRef,
    handleEditorChange,
    handleSave,
    handleCancel,
    handleDuplicate,
    confirmProps,
    blockerStatus,
    blockerProceed,
    blockerReset,
  } = useDeviceForm({
    mode: 'edit',
    deviceId: device.id,
    initialKey: device.key,
    initialDeviceModelId: device.deviceModelId,
    initialConfig: device.config,
  })

  return (
    <div data-testid="devices.editor">
      <div className="p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Keycloak Client Status */}
          <div data-testid="devices.editor.keycloak-section">
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              Keycloak Client
            </label>
            <KeycloakClientStatus deviceId={device.id} />
          </div>

          {/* Device Model (read-only, link to model editor) */}
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              Device Model
            </label>
            <div className="flex items-center">
              <Link
                to="/device-models/$modelId"
                params={{ modelId: String(device.deviceModelId) }}
                className="text-link hover:text-link-hover hover:underline"
                data-testid="devices.editor.model-display"
              >
                {device.deviceModel.name} ({device.deviceModel.code})
              </Link>
            </div>
          </div>

          {/* JSON Configuration Editor */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="block text-sm font-medium text-muted-foreground">
                Configuration (JSON)
              </label>
              {jsonError && <span className="text-sm text-destructive">{jsonError}</span>}
            </div>
            <div
              className="rounded-md border border-border overflow-hidden"
              style={{ height: '400px' }}
              data-testid="devices.editor.json-editor"
              data-state={jsonError ? 'invalid' : 'valid'}
            >
              <Editor
                height="100%"
                defaultLanguage="json"
                path="device-config.json"
                theme="vs-dark"
                value={jsonConfig}
                onChange={handleEditorChange}
                onMount={(editor) => {
                  monacoEditorRef.current = editor
                }}
                options={{
                  minimap: { enabled: false },
                  folding: true,
                  tabSize: 2,
                  scrollBeyondLastLine: false,
                  automaticLayout: true
                }}
              />
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={() => setProvisionModalOpen(true)}
                disabled={isPending}
                data-testid="devices.editor.provision-device"
                title="Provision device via USB"
              >
                <Cpu className="h-4 w-4 mr-2" />
                Provision Device
              </Button>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                onClick={handleCancel}
                disabled={isPending}
                data-testid="devices.editor.cancel"
              >
                Cancel
              </Button>
              <Button
                variant="outline"
                onClick={handleDuplicate}
                disabled={isPending}
                data-testid="devices.editor.duplicate"
              >
                Duplicate
              </Button>
              <Button
                variant="primary"
                onClick={handleSave}
                disabled={!isValid}
                loading={isPending}
                data-testid="devices.editor.save"
              >
                Save
              </Button>
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        {...confirmProps}
        contentProps={{ 'data-testid': 'devices.editor.unsaved-changes-dialog' }}
      />

      {/* Navigation blocker dialog */}
      <ConfirmDialog
        open={blockerStatus === 'blocked'}
        onOpenChange={(open) => { if (!open) blockerReset?.() }}
        onConfirm={() => blockerProceed?.()}
        title="Discard Changes"
        description="You have unsaved changes. Discard them?"
        confirmText="Discard"
        destructive
        contentProps={{ 'data-testid': 'devices.editor.navigation-blocker-dialog' }}
      />

      {/* Provision Device Modal */}
      <ProvisionDeviceModal
        open={provisionModalOpen}
        onOpenChange={setProvisionModalOpen}
        deviceId={device.id}
        deviceKey={device.key}
      />
    </div>
  )
}
