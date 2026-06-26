import { createFileRoute } from '@tanstack/react-router'
import { DeviceEditor } from '@/components/devices/device-editor'

interface NewDeviceSearch {
  config?: string
  modelId?: string
  from?: string
}

export const Route = createFileRoute('/devices/new')({
  component: NewDeviceRoute,
  validateSearch: (search: Record<string, unknown>): NewDeviceSearch => ({
    config: typeof search.config === 'string' ? search.config : undefined,
    modelId: typeof search.modelId === 'string' ? search.modelId : undefined,
    from: typeof search.from === 'string' ? search.from : undefined,
  }),
})

function NewDeviceRoute() {
  const { config, modelId, from } = Route.useSearch()

  // Parse modelId from search params if present (for duplicate flow)
  const initialModelId = modelId ? parseInt(modelId, 10) : undefined

  return (
    <div className="flex h-full flex-col">
      <DeviceEditor
        mode="new"
        initialConfig={config}
        initialDeviceModelId={isNaN(initialModelId!) ? undefined : initialModelId}
        duplicateFrom={from}
      />
    </div>
  )
}
