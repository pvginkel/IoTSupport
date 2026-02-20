import Editor from '@monaco-editor/react'
import { Button } from '@/components/primitives/button'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/primitives/dialog'
import { useDeviceForm } from '@/hooks/use-device-form'

interface DeviceEditorProps {
  mode: 'new' | 'duplicate'
  initialDeviceModelId?: number
  initialConfig?: string
  initialKey?: string
  duplicateFrom?: string
  onSave?: () => void
  onCancel?: () => void
}

/**
 * Device editor for new and duplicate modes only.
 * Edit mode is now handled by the tabbed DeviceConfigurationTab.
 */
export function DeviceEditor({
  mode,
  initialDeviceModelId,
  initialConfig,
  initialKey = '',
  duplicateFrom,
  onSave,
  onCancel,
}: DeviceEditorProps) {
  const {
    jsonConfig,
    jsonError,
    selectedModelId,
    setSelectedModelId,
    isPending,
    isValid,
    modelsLoading,
    deviceModels,
    selectedModel,
    monacoEditorRef,
    handleEditorChange,
    handleSave,
    handleCancel,
    confirmProps,
    blockerStatus,
    blockerProceed,
    blockerReset,
  } = useDeviceForm({
    mode,
    initialDeviceModelId,
    initialConfig,
    initialKey,
    duplicateFrom,
    onSave,
    onCancel,
  })

  // Title based on mode
  const getTitle = () => {
    if (mode === 'new') {
      return duplicateFrom ? (
        <>Duplicate Device: <span className="font-mono">{duplicateFrom}</span></>
      ) : 'New Device'
    }
    return <>Duplicate Device: <span className="font-mono">{initialKey}</span></>
  }

  return (
    <div className="flex h-full flex-col" data-testid="devices.editor">
      <div className="border-b border-border bg-background p-4">
        <div className="flex items-center justify-between">
          {/* Title */}
          <h1 className="text-2xl font-bold text-foreground">
            {getTitle()}
          </h1>
          {/* Form actions */}
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
          {/* Device Model Selection */}
          <div>
            <label htmlFor="device-model" className="block text-sm font-medium text-muted-foreground mb-2">
              Device Model
            </label>
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
              style={{ height: '300px' }}
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
        open={blockerStatus === 'blocked'}
        onOpenChange={(open) => { if (!open) blockerReset?.() }}
        onConfirm={() => blockerProceed?.()}
        title="Discard Changes"
        description="You have unsaved changes. Discard them?"
        confirmText="Discard"
        destructive
        contentProps={{ 'data-testid': 'devices.editor.navigation-blocker-dialog' }}
      />
    </div>
  )
}
