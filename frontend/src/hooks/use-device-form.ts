import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useNavigate, useBlocker } from '@tanstack/react-router'
import { useCreateDevice, useUpdateDevice } from '@/hooks/use-devices'
import { useDeviceModels, useDeviceModel } from '@/hooks/use-device-models'
import { useConfirm } from '@/hooks/use-confirm'
import { useFormInstrumentation } from '@/hooks/use-form-instrumentation'
import { configureMonacoSchemaValidation } from '@/lib/utils/monaco-schema'
import { setDeviceTabPreference } from '@/lib/utils/device-tab-preference'

const DEFAULT_TEMPLATE = JSON.stringify({
  deviceName: '',
  deviceEntityId: '',
  enableOTA: false
}, null, 2)

interface UseDeviceFormOptions {
  mode: 'new' | 'edit' | 'duplicate'
  deviceId?: number
  initialKey?: string
  initialDeviceModelId?: number
  initialConfig?: string
  /** Source device key shown in the title during duplicate flow (not used by the hook) */
  duplicateFrom?: string
  onSave?: () => void
  onCancel?: () => void
}

export function useDeviceForm({
  mode,
  deviceId,
  initialKey = '',
  initialDeviceModelId,
  initialConfig = DEFAULT_TEMPLATE,
  // duplicateFrom is accepted for callers' convenience but not used in form logic
  onSave: onSaveCallback,
  onCancel: onCancelCallback,
}: UseDeviceFormOptions) {
  const navigate = useNavigate()
  const createDevice = useCreateDevice()
  const updateDevice = useUpdateDevice()
  const { deviceModels, isLoading: modelsLoading } = useDeviceModels()
  const { confirm, confirmProps } = useConfirm()
  const monacoEditorRef = useRef<unknown>(null)

  // Form instrumentation for Playwright tests
  const formId = mode === 'edit' ? 'DeviceEditor_edit' : mode === 'duplicate' ? 'DeviceEditor_duplicate' : 'DeviceEditor_new'
  const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({ formId, isOpen: true })

  // Device model is selectable for new devices, fixed for edits
  const [selectedModelId, setSelectedModelId] = useState<number | undefined>(initialDeviceModelId)

  // Fetch full device model (with schema) for Monaco validation
  const modelIdForSchema = mode === 'edit' ? initialDeviceModelId : selectedModelId
  const { deviceModel: fullDeviceModel } = useDeviceModel(modelIdForSchema)
  const [jsonConfig, setJsonConfig] = useState(initialConfig)
  const [jsonError, setJsonError] = useState<string | null>(null)

  const originalModelId = initialDeviceModelId
  const originalJson = initialConfig

  // Track dirty state
  const isDirty = useMemo(() => {
    if (mode === 'edit') {
      return jsonConfig !== originalJson
    }
    const modelChanged = selectedModelId !== originalModelId
    const jsonChanged = jsonConfig !== originalJson
    return modelChanged || jsonChanged
  }, [selectedModelId, jsonConfig, originalModelId, originalJson, mode])

  // Use ref to track if we're intentionally navigating (bypassing blocker)
  const isNavigatingRef = useRef(false)

  // Navigation blocker for unsaved changes
  const { proceed, reset, status } = useBlocker({
    shouldBlockFn: () => isDirty && !isNavigatingRef.current,
    enableBeforeUnload: isDirty,
    withResolver: true,
  })

  // Configure Monaco schema validation when device model has a config schema
  useEffect(() => {
    if (fullDeviceModel?.configSchema) {
      try {
        const schema = JSON.parse(fullDeviceModel.configSchema)
        configureMonacoSchemaValidation(schema, 'device-config.json')
      } catch {
        // Invalid schema JSON, skip validation
      }
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
      // Use functional update to only change state if value actually differs.
      // Monaco can fire onChange on focus/click even when content is unchanged.
      setJsonConfig(prev => prev === value ? prev : value)
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

    isNavigatingRef.current = true
    trackSubmit({ deviceId, mode })

    if (mode === 'edit') {
      if (deviceId === undefined) {
        setJsonError('Device ID is required for update')
        isNavigatingRef.current = false
        trackError({ error: 'Device ID is required for update' })
        return
      }

      updateDevice.mutate(
        { id: deviceId, config: jsonConfig },
        {
          onSuccess: () => {
            trackSuccess({ deviceId })
            onSaveCallback?.()
            // Navigate to the device's logs tab so the user can see immediate
            // feedback that the device is operating with the new configuration.
            setDeviceTabPreference('logs')
            navigate({ to: '/devices/$deviceId/logs', params: { deviceId: String(deviceId) } })
          },
          onError: (err) => {
            isNavigatingRef.current = false
            trackError({ error: err instanceof Error ? err.message : 'Unknown error' })
          }
        }
      )
    } else {
      createDevice.mutate(
        { deviceModelId: selectedModelId!, config: jsonConfig },
        {
          onSuccess: () => {
            trackSuccess({ mode })
            onSaveCallback?.()
            navigate({ to: '/devices' })
          },
          onError: (err) => {
            isNavigatingRef.current = false
            trackError({ error: err instanceof Error ? err.message : 'Unknown error' })
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

      isNavigatingRef.current = true
    }

    onCancelCallback?.()
    navigate({ to: '/devices' })
  }, [isDirty, confirm, onCancelCallback, navigate])

  const handleDuplicate = useCallback(() => {
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

  // Get selected model name for display
  const selectedModel = deviceModels.find(m => m.id === selectedModelId)

  return {
    // State
    jsonConfig,
    jsonError,
    selectedModelId,
    setSelectedModelId,
    isDirty,
    isPending,
    isValid,
    modelsLoading,
    deviceModels,
    selectedModel,
    fullDeviceModel,
    monacoEditorRef,

    // Actions
    handleEditorChange,
    handleSave,
    handleCancel,
    handleDuplicate,

    // Dialog props
    confirmProps,
    blockerStatus: status,
    blockerProceed: proceed,
    blockerReset: reset,
  }
}
