import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate, useBlocker } from '@tanstack/react-router'
import Editor from '@monaco-editor/react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useSaveDevice, useDeleteDevice } from '@/hooks/use-devices'
import { ConfirmDialog } from '@/components/ui/dialog'
import { useConfirm } from '@/hooks/use-confirm'

interface DeviceEditorProps {
  mode: 'new' | 'edit' | 'duplicate'
  initialMacAddress?: string
  initialConfig?: Record<string, unknown>
  duplicateFrom?: string
  onSave?: () => void
  onCancel?: () => void
}

const DEFAULT_TEMPLATE = {
  deviceName: '',
  deviceEntityId: '',
  enableOTA: false
}

export function DeviceEditor({
  mode,
  initialMacAddress = '',
  initialConfig = DEFAULT_TEMPLATE,
  duplicateFrom,
  onSave: onSaveCallback,
  onCancel: onCancelCallback
}: DeviceEditorProps) {
  const navigate = useNavigate()
  const saveDevice = useSaveDevice()
  const deleteDevice = useDeleteDevice()
  const { confirm, confirmProps } = useConfirm()

  const [macAddress, setMacAddress] = useState(mode === 'duplicate' ? '' : initialMacAddress)
  const [jsonConfig, setJsonConfig] = useState(JSON.stringify(initialConfig, null, 2))
  const [jsonError, setJsonError] = useState<string | null>(null)

  const originalMac = mode === 'duplicate' ? '' : initialMacAddress
  const originalJson = JSON.stringify(initialConfig, null, 2)

  // Track dirty state - computed from state
  const isDirty = useMemo(() => {
    const macChanged = macAddress !== originalMac
    const jsonChanged = jsonConfig !== originalJson
    return macChanged || jsonChanged
  }, [macAddress, jsonConfig, originalMac, originalJson])

  const originalMacRef = useRef(initialMacAddress)
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
    if (!macAddress.trim()) {
      setJsonError('MAC address is required')
      return
    }

    if (!validateJson(jsonConfig)) {
      return
    }

    const configContent = JSON.parse(jsonConfig)
    isNavigatingRef.current = true

    // Determine if we should prevent overwriting existing config:
    // - For new devices: always set allow_overwrite to false
    // - For edit mode with MAC change: set allow_overwrite to false (new MAC might exist)
    // - For edit mode without MAC change: allow_overwrite to true
    const isNewOrMacChanged = mode === 'new' || (mode === 'edit' && macAddress !== originalMacRef.current)
    const allowOverwrite = !isNewOrMacChanged

    // Build the config request
    const configRequest = { content: configContent, allow_overwrite: allowOverwrite }

    // Handle MAC rename for edit mode
    if (mode === 'edit' && macAddress !== originalMacRef.current && originalMacRef.current) {
      try {
        // Save to new MAC
        await saveDevice.mutateAsync({
          macAddress,
          config: configRequest
        })

        // Delete old MAC (partial success is acceptable - new device saved)
        try {
          await deleteDevice.mutateAsync({ macAddress: originalMacRef.current })
        } catch {
          // Partial success - new device saved but old not deleted
          // User will see both devices in list, old one can be manually deleted
        }

        onSaveCallback?.()
        navigate({ to: '/devices' })
      } catch {
        // Error already handled by mutation hook toast
        isNavigatingRef.current = false
      }
    } else {
      // Normal save (new or edit without MAC change)
      saveDevice.mutate(
        { macAddress, config: configRequest },
        {
          onSuccess: () => {
            onSaveCallback?.()
            navigate({ to: '/devices' })
          },
          onError: () => {
            isNavigatingRef.current = false
          }
        }
      )
    }
  }, [macAddress, jsonConfig, mode, saveDevice, deleteDevice, validateJson, onSaveCallback, navigate])

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
        from: initialMacAddress,
      }
    })
  }, [jsonConfig, initialMacAddress, navigate])

  const isValid = !!macAddress.trim() && !jsonError && !saveDevice.isPending

  // Title based on mode
  const getTitle = () => {
    if (mode === 'new') {
      return duplicateFrom ? `Duplicate Device: ${duplicateFrom}` : 'New Device'
    }
    if (mode === 'edit') {
      return `Edit Device: ${initialMacAddress}`
    }
    return `Duplicate Device: ${initialMacAddress}`
  }

  return (
    <div className="flex h-full flex-col" data-testid="devices.editor">
      <div className="border-b border-zinc-800 bg-zinc-950 p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-zinc-50">
            {getTitle()}
          </h1>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={saveDevice.isPending}
              data-testid="devices.editor.cancel"
            >
              Cancel
            </Button>
            {mode === 'edit' && (
              <Button
                variant="outline"
                onClick={handleDuplicate}
                disabled={saveDevice.isPending}
                data-testid="devices.editor.duplicate"
              >
                Duplicate
              </Button>
            )}
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={!isValid}
              loading={saveDevice.isPending}
              data-testid="devices.editor.save"
            >
              Save
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          <div>
            <label htmlFor="mac-address" className="block text-sm font-medium text-zinc-300 mb-2">
              MAC Address
            </label>
            <Input
              id="mac-address"
              value={macAddress}
              onChange={(e) => setMacAddress(e.target.value)}
              placeholder="aa-bb-cc-dd-ee-ff"
              disabled={saveDevice.isPending}
              data-testid="devices.editor.mac-input"
            />
            <p className="mt-1 text-xs text-zinc-500">Format: aa-bb-cc-dd-ee-ff (hyphen-separated, lowercase)</p>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="json-config" className="block text-sm font-medium text-zinc-300">
                Configuration (JSON)
              </label>
              {jsonError && <span className="text-sm text-red-400">{jsonError}</span>}
            </div>
            <div
              className="rounded-md border border-zinc-700 overflow-hidden"
              style={{ height: '425px' }}
              data-testid="devices.editor.json-editor"
              data-state={jsonError ? 'invalid' : 'valid'}
            >
              <Editor
                height="100%"
                defaultLanguage="json"
                theme="vs-dark"
                value={jsonConfig}
                onChange={handleEditorChange}
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
    </div>
  )
}
