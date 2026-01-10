import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from '@tanstack/react-router'
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

  // Beforeunload warning
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
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

    // Handle MAC rename for edit mode
    if (mode === 'edit' && macAddress !== originalMacRef.current && originalMacRef.current) {
      try {
        // Save to new MAC
        await saveDevice.mutateAsync({
          macAddress,
          config: { content: configContent }
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
      }
    } else {
      // Normal save (new or edit without MAC change)
      saveDevice.mutate(
        { macAddress, config: { content: configContent } },
        {
          onSuccess: () => {
            onSaveCallback?.()
            navigate({ to: '/devices' })
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
    }

    onCancelCallback?.()
    navigate({ to: '/devices' })
  }, [isDirty, confirm, onCancelCallback, navigate])

  const handleDuplicate = useCallback(() => {
    if (initialMacAddress) {
      navigate({ to: '/devices/$macAddress/duplicate', params: { macAddress: initialMacAddress } })
    }
  }, [initialMacAddress, navigate])

  const isValid = !!macAddress.trim() && !jsonError && !saveDevice.isPending

  return (
    <div className="flex h-full flex-col" data-testid="devices.editor">
      <div className="border-b border-zinc-800 bg-zinc-950 p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-zinc-50">
            {mode === 'new' && 'New Device'}
            {mode === 'edit' && `Edit Device: ${initialMacAddress}`}
            {mode === 'duplicate' && `Duplicate Device: ${initialMacAddress}`}
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
              placeholder="AA:BB:CC:DD:EE:FF"
              disabled={saveDevice.isPending}
              data-testid="devices.editor.mac-input"
            />
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
              style={{ height: '500px' }}
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
    </div>
  )
}
