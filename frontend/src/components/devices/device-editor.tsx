import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate, useBlocker, Link } from '@tanstack/react-router'
import Editor from '@monaco-editor/react'
import { Cpu, ExternalLink, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { useCreateDevice, useUpdateDevice, useDeviceKeycloakStatus, useSyncDeviceKeycloak } from '@/hooks/use-devices'
import { useDeviceModels, useDeviceModel } from '@/hooks/use-device-models'
import { ConfirmDialog } from '@/components/ui/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useFormInstrumentation } from '@/lib/test/form-instrumentation'
import { configureMonacoSchemaValidation } from '@/lib/utils/monaco-schema'
import { ProvisionDeviceModal } from './provision-device-modal'

interface DeviceEditorProps {
  mode: 'new' | 'edit' | 'duplicate'
  // For edit mode: the device ID (required for updates)
  deviceId?: number
  // For edit mode: the device key (read-only display)
  initialKey?: string
  // Device model ID (read-only in edit mode, selectable in new/duplicate mode)
  initialDeviceModelId?: number
  // Device model info for display in edit mode
  initialDeviceModel?: { code: string; name: string }
  initialConfig?: Record<string, unknown>
  duplicateFrom?: string  // Source device key for duplicate mode
  onSave?: () => void
  onCancel?: () => void
}

const DEFAULT_TEMPLATE = {
  deviceName: '',
  deviceEntityId: '',
  enableOTA: false
}

// Component to display Keycloak client status with ability to recreate/sync
interface KeycloakClientStatusProps {
  deviceId: number
}

// Custom hook to manage blinking animation that continues for minimum 2 blinks
function useBlinkingSync(syncMutation: ReturnType<typeof useSyncDeviceKeycloak>, deviceId: number) {
  const [blinkPhase, setBlinkPhase] = useState<number | null>(null) // null = not blinking, number = current phase
  const syncCompletedRef = useRef(false)

  const isBlinking = blinkPhase !== null

  // Handle blinking animation
  useEffect(() => {
    if (blinkPhase === null) return

    const timeout = setTimeout(() => {
      const nextPhase = blinkPhase + 1
      // Stop after sync completes AND we've done at least 2 full blinks (4 phases)
      if (syncCompletedRef.current && nextPhase >= 4) {
        setBlinkPhase(null)
      } else {
        setBlinkPhase(nextPhase)
      }
    }, 400)

    return () => clearTimeout(timeout)
  }, [blinkPhase])

  const startSync = useCallback(() => {
    setBlinkPhase(0)
    syncCompletedRef.current = false
    syncMutation.mutate(
      { deviceId },
      {
        onSuccess: () => {
          syncCompletedRef.current = true
        },
        onError: () => {
          syncCompletedRef.current = true
        }
      }
    )
  }, [syncMutation, deviceId])

  // Icon is visible on even phases (0, 2, 4...) or when not blinking
  const iconVisible = blinkPhase === null || blinkPhase % 2 === 0

  return { isBlinking, iconVisible, startSync }
}

function KeycloakClientStatus({ deviceId }: KeycloakClientStatusProps) {
  const { status, isLoading, isError } = useDeviceKeycloakStatus(deviceId)
  const syncKeycloak = useSyncDeviceKeycloak()
  const { isBlinking, iconVisible, startSync } = useBlinkingSync(syncKeycloak, deviceId)

  // Show loading state
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>Checking Keycloak status...</span>
      </div>
    )
  }

  // Show error state
  if (isError || !status) {
    return (
      <span className="text-muted-foreground" data-testid="devices.editor.keycloak-status-error">
        Unable to check Keycloak status
      </span>
    )
  }

  // Show status with appropriate action
  if (status.exists) {
    return (
      <div className="flex items-center gap-2">
        <span
          className="font-mono text-green-400"
          data-testid="devices.editor.keycloak-client-id"
        >
          {status.clientId}
        </span>
        {status.consoleUrl && (
          <a
            href={status.consoleUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground"
            title="Open in Keycloak console"
            data-testid="devices.editor.keycloak-console-link"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
        <button
          onClick={startSync}
          disabled={isBlinking}
          className="cursor-pointer text-muted-foreground hover:text-foreground disabled:cursor-not-allowed"
          title="Resync Keycloak client"
          data-testid="devices.editor.keycloak-sync"
        >
          <RefreshCw
            className={`h-4 w-4 transition-opacity ${iconVisible ? 'opacity-100' : 'opacity-0'}`}
          />
        </button>
      </div>
    )
  }

  // Client doesn't exist - show recreate option
  return (
    <div className="flex items-center gap-3">
      <span className="text-amber-400" data-testid="devices.editor.keycloak-status-missing">
        Client not found in Keycloak
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={startSync}
        disabled={isBlinking}
        loading={isBlinking}
        data-testid="devices.editor.keycloak-recreate"
      >
        <RefreshCw className="h-3 w-3 mr-1" />
        Recreate Client
      </Button>
    </div>
  )
}

export function DeviceEditor({
  mode,
  deviceId,
  initialKey = '',
  initialDeviceModelId,
  initialDeviceModel,
  initialConfig = DEFAULT_TEMPLATE,
  duplicateFrom,
  onSave: onSaveCallback,
  onCancel: onCancelCallback
}: DeviceEditorProps) {
  const navigate = useNavigate()
  const createDevice = useCreateDevice()
  const updateDevice = useUpdateDevice()
  const { deviceModels, isLoading: modelsLoading } = useDeviceModels()
  const { confirm, confirmProps } = useConfirm()
  const monacoEditorRef = useRef<unknown>(null)

  // Provisioning modal state
  const [provisionModalOpen, setProvisionModalOpen] = useState(false)

  // Form instrumentation for Playwright tests
  const formId = mode === 'edit' ? 'DeviceEditor_edit' : mode === 'duplicate' ? 'DeviceEditor_duplicate' : 'DeviceEditor_new'
  const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({ formId })

  // Device model is selectable for new devices, fixed for edits
  const [selectedModelId, setSelectedModelId] = useState<number | undefined>(
    mode === 'duplicate' ? initialDeviceModelId : initialDeviceModelId
  )

  // Fetch full device model (with schema) for Monaco validation
  // In edit mode, model is fixed; in new/duplicate mode, use the currently selected model
  const modelIdForSchema = mode === 'edit' ? initialDeviceModelId : selectedModelId
  const { deviceModel: fullDeviceModel } = useDeviceModel(modelIdForSchema)
  const [jsonConfig, setJsonConfig] = useState(JSON.stringify(initialConfig, null, 2))
  const [jsonError, setJsonError] = useState<string | null>(null)

  const originalModelId = mode === 'duplicate' ? initialDeviceModelId : initialDeviceModelId
  const originalJson = JSON.stringify(initialConfig, null, 2)

  // Track dirty state - computed from state
  const isDirty = useMemo(() => {
    // In edit mode, model is not editable, so only check JSON
    if (mode === 'edit') {
      return jsonConfig !== originalJson
    }
    const modelChanged = selectedModelId !== originalModelId
    const jsonChanged = jsonConfig !== originalJson
    return modelChanged || jsonChanged
  }, [selectedModelId, jsonConfig, originalModelId, originalJson, mode])

  // Use ref to track if we're intentionally navigating (bypassing blocker)
  const isNavigatingRef = useRef(false)

  // Navigation blocker for unsaved changes (handles back/forward and link clicks)
  const { proceed, reset, status } = useBlocker({
    shouldBlockFn: () => isDirty && !isNavigatingRef.current,
    withResolver: true,
  })

  // Beforeunload warning for page refresh/close
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty && !isNavigatingRef.current) {
        e.preventDefault()
        e.returnValue = ''
      }
    }

    if (isDirty) {
      window.addEventListener('beforeunload', handleBeforeUnload)
      return () => window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }, [isDirty])

  // Configure Monaco schema validation when device model has a config schema
  useEffect(() => {
    if (fullDeviceModel?.configSchema) {
      configureMonacoSchemaValidation(
        fullDeviceModel.configSchema,
        'device-config.json'  // Must match the `path` prop on the Editor component
      )
    }
  }, [fullDeviceModel?.configSchema])

  // Validate JSON
  const validateJson = useCallback((value: string): boolean => {
    try {
      JSON.parse(value)
      setJsonError(null)
      return true
    } catch (error) {
      setJsonError(error instanceof Error ? error.message : 'Invalid JSON')
      return false
    }
  }, [])

  const handleEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setJsonConfig(value)
      validateJson(value)
    }
  }, [validateJson])

  const handleSave = useCallback(async () => {
    // Model selection validation only for new devices
    if (mode !== 'edit' && !selectedModelId) {
      setJsonError('Device model is required')
      return
    }

    if (!validateJson(jsonConfig)) {
      return
    }

    const configContent = JSON.parse(jsonConfig)
    isNavigatingRef.current = true
    trackSubmit({ deviceId, mode })

    if (mode === 'edit') {
      // Update existing device by ID
      if (deviceId === undefined) {
        setJsonError('Device ID is required for update')
        isNavigatingRef.current = false
        trackError('Device ID is required for update')
        return
      }

      updateDevice.mutate(
        { id: deviceId, config: configContent },
        {
          onSuccess: () => {
            trackSuccess({ deviceId })
            onSaveCallback?.()
            navigate({ to: '/devices' })
          },
          onError: (err) => {
            isNavigatingRef.current = false
            trackError(err instanceof Error ? err.message : 'Unknown error')
          }
        }
      )
    } else {
      // Create new device (new or duplicate mode)
      createDevice.mutate(
        { deviceModelId: selectedModelId!, config: configContent },
        {
          onSuccess: () => {
            trackSuccess({ mode })
            onSaveCallback?.()
            navigate({ to: '/devices' })
          },
          onError: (err) => {
            isNavigatingRef.current = false
            trackError(err instanceof Error ? err.message : 'Unknown error')
          }
        }
      )
    }
  }, [selectedModelId, jsonConfig, mode, deviceId, createDevice, updateDevice, validateJson, onSaveCallback, navigate, trackSubmit, trackSuccess, trackError])

  const handleCancel = useCallback(async () => {
    if (isDirty) {
      const confirmed = await confirm({
        title: 'Discard Changes',
        description: 'You have unsaved changes. Discard them?',
        confirmText: 'Discard',
        destructive: true
      })

      if (!confirmed) return

      // Set ref to bypass blocker during navigation
      isNavigatingRef.current = true
    }

    onCancelCallback?.()
    navigate({ to: '/devices' })
  }, [isDirty, confirm, onCancelCallback, navigate])

  const handleDuplicate = useCallback(() => {
    // Set ref to bypass blocker during navigation
    isNavigatingRef.current = true
    navigate({
      to: '/devices/new',
      search: {
        config: jsonConfig,
        modelId: initialDeviceModelId?.toString(),
        from: initialKey,
      }
    })
  }, [jsonConfig, initialDeviceModelId, initialKey, navigate])

  const isPending = createDevice.isPending || updateDevice.isPending
  const isValid = (mode === 'edit' || !!selectedModelId) && !jsonError && !isPending

  // Title based on mode
  const getTitle = () => {
    if (mode === 'new') {
      return duplicateFrom ? `Duplicate Device: ${duplicateFrom}` : 'New Device'
    }
    if (mode === 'edit') {
      return `Edit Device: ${initialKey}`
    }
    return `Duplicate Device: ${initialKey}`
  }

  // Get selected model name for display
  const selectedModel = deviceModels.find(m => m.id === selectedModelId)

  return (
    <div className="flex h-full flex-col" data-testid="devices.editor">
      <div className="border-b border-border bg-background p-4">
        <div className="flex items-center justify-between">
          {/* Left side: Title */}
          <h1 className="text-2xl font-bold text-foreground">
            {getTitle()}
          </h1>
          {/* Right side: Device actions + separator + form actions */}
          <div className="flex items-center gap-2">
            {/* Provision Device button - only in edit mode */}
            {mode === 'edit' && deviceId && (
              <>
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
                {/* Vertical separator */}
                <div className="h-6 w-px bg-border mx-1" />
              </>
            )}
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={isPending}
              data-testid="devices.editor.cancel"
            >
              Cancel
            </Button>
            {mode === 'edit' && (
              <Button
                variant="outline"
                onClick={handleDuplicate}
                disabled={isPending}
                data-testid="devices.editor.duplicate"
              >
                Duplicate
              </Button>
            )}
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

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Device Key (read-only in edit mode) */}
          {mode === 'edit' && initialKey && (
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-2">
                Device Key
              </label>
              <div className="flex items-center">
                <span className="font-mono text-foreground" data-testid="devices.editor.key-display">
                  {initialKey}
                </span>
              </div>
            </div>
          )}

          {/* Keycloak Client Status (edit mode only) */}
          {mode === 'edit' && deviceId && (
            <div data-testid="devices.editor.keycloak-section">
              <label className="block text-sm font-medium text-muted-foreground mb-2">
                Keycloak Client
              </label>
              <KeycloakClientStatus deviceId={deviceId} />
            </div>
          )}

          {/* Device Model Selection */}
          <div>
            <label htmlFor="device-model" className="block text-sm font-medium text-muted-foreground mb-2">
              Device Model
            </label>
            {mode === 'edit' ? (
              // In edit mode, model is read-only but clickable to navigate to model editor
              <div className="flex items-center">
                {initialDeviceModelId ? (
                  <Link
                    to="/device-models/$modelId"
                    params={{ modelId: String(initialDeviceModelId) }}
                    className="text-link hover:text-link-hover hover:underline"
                    data-testid="devices.editor.model-display"
                  >
                    {initialDeviceModel ? `${initialDeviceModel.name} (${initialDeviceModel.code})` : 'Unknown'}
                  </Link>
                ) : (
                  <span className="text-foreground" data-testid="devices.editor.model-display">
                    Unknown
                  </span>
                )}
              </div>
            ) : (
              <>
                <Select
                  value={selectedModelId?.toString() ?? ''}
                  onValueChange={(value: string) => setSelectedModelId(value ? parseInt(value, 10) : undefined)}
                  disabled={isPending || modelsLoading}
                >
                  <SelectTrigger data-testid="devices.editor.model-select">
                    <SelectValue placeholder={modelsLoading ? 'Loading models...' : 'Select a device model'} />
                  </SelectTrigger>
                  <SelectContent>
                    {deviceModels.map((model) => (
                      <SelectItem key={model.id} value={model.id.toString()}>
                        {model.name} ({model.code})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedModel && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {selectedModel.deviceCount} device{selectedModel.deviceCount !== 1 ? 's' : ''} using this model
                    {selectedModel.firmwareVersion && ` | Firmware: ${selectedModel.firmwareVersion}`}
                  </p>
                )}
              </>
            )}
          </div>

          {/* JSON Configuration */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="json-config" className="block text-sm font-medium text-muted-foreground">
                Configuration (JSON)
              </label>
              {jsonError && <span className="text-sm text-destructive">{jsonError}</span>}
            </div>
            <div
              className="rounded-md border border-border overflow-hidden"
              style={{ height: '425px' }}
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
        </div>
      </div>

      <ConfirmDialog
        {...confirmProps}
        contentProps={{ 'data-testid': 'devices.editor.unsaved-changes-dialog' }}
      />

      {/* Navigation blocker dialog */}
      <ConfirmDialog
        open={status === 'blocked'}
        onOpenChange={(open) => { if (!open) reset?.() }}
        onConfirm={() => proceed?.()}
        title="Discard Changes"
        description="You have unsaved changes. Discard them?"
        confirmText="Discard"
        destructive
        contentProps={{ 'data-testid': 'devices.editor.navigation-blocker-dialog' }}
      />

      {/* Provision Device Modal */}
      {mode === 'edit' && deviceId && (
        <ProvisionDeviceModal
          open={provisionModalOpen}
          onOpenChange={setProvisionModalOpen}
          deviceId={deviceId}
          deviceKey={initialKey}
        />
      )}
    </div>
  )
}
