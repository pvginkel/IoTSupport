import { useState, useCallback, useRef, useMemo } from 'react'
import { useNavigate, useBlocker } from '@tanstack/react-router'
import Editor from '@monaco-editor/react'
import { Button } from '@/components/primitives/button'
import { Input } from '@/components/primitives/input'
import { useCreateDeviceModel, useUpdateDeviceModel } from '@/hooks/use-device-models'
import { ConfirmDialog } from '@/components/primitives/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useFormInstrumentation } from '@/hooks/use-form-instrumentation'

interface DeviceModelEditorProps {
  mode: 'new' | 'edit'
  modelId?: number
  initialCode?: string
  initialName?: string
  initialConfigSchema?: string | null
  onSave?: () => void
  onCancel?: () => void
}

const DEFAULT_SCHEMA = {
  type: 'object',
  properties: {
    deviceName: { type: 'string', description: 'Human-readable device name' },
    deviceEntityId: { type: 'string', description: 'Entity identifier' },
    enableOTA: { type: 'boolean', description: 'Enable OTA updates' }
  },
  required: ['deviceName', 'deviceEntityId']
}

export function DeviceModelEditor({
  mode,
  modelId,
  initialCode = '',
  initialName = '',
  initialConfigSchema = null,
  onSave: onSaveCallback,
  onCancel: onCancelCallback
}: DeviceModelEditorProps) {
  const navigate = useNavigate()
  const createDeviceModel = useCreateDeviceModel()
  const updateDeviceModel = useUpdateDeviceModel()
  const { confirm, confirmProps } = useConfirm()

  // Form instrumentation for Playwright tests
  const formId = mode === 'edit' ? 'DeviceModelEditor_edit' : 'DeviceModelEditor_new'
  const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({ formId, isOpen: true })

  // Code is editable only for new models
  const [code, setCode] = useState(initialCode)
  const [name, setName] = useState(initialName)
  const [jsonSchema, setJsonSchema] = useState(initialConfigSchema ?? '')
  const [jsonError, setJsonError] = useState<string | null>(null)

  const originalCode = initialCode
  const originalName = initialName
  const originalSchema = initialConfigSchema ?? ''

  // Track dirty state
  const isDirty = useMemo(() => {
    if (mode === 'edit') {
      // In edit mode, code cannot change
      return name !== originalName || jsonSchema !== originalSchema
    }
    return code !== originalCode || name !== originalName || jsonSchema !== originalSchema
  }, [code, name, jsonSchema, originalCode, originalName, originalSchema, mode])

  // Use ref to track if we're intentionally navigating
  const isNavigatingRef = useRef(false)

  // Navigation blocker for unsaved changes (handles back/forward, link clicks,
  // and page refresh/close via enableBeforeUnload)
  const { proceed, reset, status } = useBlocker({
    shouldBlockFn: () => isDirty && !isNavigatingRef.current,
    enableBeforeUnload: isDirty,
    withResolver: true,
  })

  // Validate JSON schema
  const validateSchema = useCallback((value: string): boolean => {
    if (!value.trim()) {
      // Empty schema is valid (no validation)
      setJsonError(null)
      return true
    }
    try {
      const parsed = JSON.parse(value)
      // Basic JSON Schema validation - must be an object
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        setJsonError('Schema must be a JSON object')
        return false
      }
      setJsonError(null)
      return true
    } catch (error) {
      setJsonError(error instanceof Error ? error.message : 'Invalid JSON')
      return false
    }
  }, [])

  const handleSchemaChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setJsonSchema(value)
      validateSchema(value)
    }
  }, [validateSchema])

  const handleSave = useCallback(async () => {
    // Validate required fields
    if (!code.trim()) {
      setJsonError('Code is required')
      return
    }
    if (!name.trim()) {
      setJsonError('Name is required')
      return
    }

    if (!validateSchema(jsonSchema)) {
      return
    }

    const configSchema = jsonSchema.trim() || null
    isNavigatingRef.current = true
    trackSubmit({ modelId, mode })

    if (mode === 'edit') {
      if (modelId === undefined) {
        setJsonError('Model ID is required for update')
        isNavigatingRef.current = false
        trackError({ error: 'Model ID is required for update' })
        return
      }

      updateDeviceModel.mutate(
        { id: modelId, name, configSchema },
        {
          onSuccess: () => {
            trackSuccess({ modelId })
            onSaveCallback?.()
            navigate({ to: '/device-models' })
          },
          onError: (err) => {
            isNavigatingRef.current = false
            trackError({ error: err instanceof Error ? err.message : 'Unknown error' })
          }
        }
      )
    } else {
      createDeviceModel.mutate(
        { code, name, configSchema },
        {
          onSuccess: () => {
            trackSuccess({ mode })
            onSaveCallback?.()
            navigate({ to: '/device-models' })
          },
          onError: (err) => {
            isNavigatingRef.current = false
            trackError({ error: err instanceof Error ? err.message : 'Unknown error' })
          }
        }
      )
    }
  }, [code, name, jsonSchema, mode, modelId, createDeviceModel, updateDeviceModel, validateSchema, onSaveCallback, navigate, trackSubmit, trackSuccess, trackError])

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
    navigate({ to: '/device-models' })
  }, [isDirty, confirm, onCancelCallback, navigate])

  const handleInsertTemplate = useCallback(() => {
    setJsonSchema(JSON.stringify(DEFAULT_SCHEMA, null, 2))
    validateSchema(JSON.stringify(DEFAULT_SCHEMA))
  }, [validateSchema])

  const isPending = createDeviceModel.isPending || updateDeviceModel.isPending
  const isValid = !!code.trim() && !!name.trim() && !jsonError && !isPending

  const getTitle = () => {
    if (mode === 'new') {
      return 'New Device Model'
    }
    return `Edit Device Model: ${initialCode}`
  }

  return (
    <div className="flex h-full flex-col" data-testid="device-models.editor">
      <div className="border-b border-border bg-background p-4">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-foreground">
            {getTitle()}
          </h1>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={handleCancel}
              disabled={isPending}
              data-testid="device-models.editor.cancel"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={!isValid}
              loading={isPending}
              data-testid="device-models.editor.save"
            >
              Save
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Model Code */}
          <div>
            <label htmlFor="model-code" className="block text-sm font-medium text-muted-foreground mb-2">
              Model Code
            </label>
            {mode === 'edit' ? (
              <div className="flex items-center">
                <span className="font-mono text-foreground" data-testid="device-models.editor.code-display">
                  {initialCode}
                </span>
              </div>
            ) : (
              <>
                <Input
                  id="model-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="my_sensor_v1"
                  disabled={isPending}
                  data-testid="device-models.editor.code-input"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Unique identifier for this model (lowercase, alphanumeric, underscores allowed)
                </p>
              </>
            )}
          </div>

          {/* Model Name */}
          <div>
            <label htmlFor="model-name" className="block text-sm font-medium text-muted-foreground mb-2">
              Model Name
            </label>
            <Input
              id="model-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My Sensor v1.0"
              disabled={isPending}
              data-testid="device-models.editor.name-input"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Human-readable name for this device model
            </p>
          </div>

          {/* JSON Schema */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label htmlFor="json-schema" className="block text-sm font-medium text-muted-foreground">
                Configuration Schema (JSON Schema)
              </label>
              <div className="flex items-center gap-2">
                {jsonError && <span className="text-sm text-destructive">{jsonError}</span>}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleInsertTemplate}
                  disabled={isPending}
                  data-testid="device-models.editor.insert-template"
                >
                  Insert Template
                </Button>
              </div>
            </div>
            <div
              className="rounded-md border border-border overflow-hidden"
              style={{ height: '350px' }}
              data-testid="device-models.editor.schema-editor"
              data-state={jsonError ? 'invalid' : 'valid'}
            >
              <Editor
                height="100%"
                defaultLanguage="json"
                theme="vs-dark"
                value={jsonSchema}
                onChange={handleSchemaChange}
                options={{
                  minimap: { enabled: false },
                  folding: true,
                  tabSize: 2,
                  scrollBeyondLastLine: false,
                  automaticLayout: true
                }}
              />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Optional JSON Schema to validate device configurations. Leave empty for no validation.
            </p>
          </div>
        </div>
      </div>

      <ConfirmDialog
        {...confirmProps}
        contentProps={{ 'data-testid': 'device-models.editor.unsaved-changes-dialog' }}
      />

      <ConfirmDialog
        open={status === 'blocked'}
        onOpenChange={(open) => { if (!open) reset?.() }}
        onConfirm={() => proceed?.()}
        title="Discard Changes"
        description="You have unsaved changes. Discard them?"
        confirmText="Discard"
        destructive
        contentProps={{ 'data-testid': 'device-models.editor.navigation-blocker-dialog' }}
      />
    </div>
  )
}
