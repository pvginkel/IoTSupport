import { createFileRoute } from '@tanstack/react-router'
import { DeviceEditor } from '@/components/devices/device-editor'

interface NewDeviceSearch {
  config?: string
  from?: string
}

export const Route = createFileRoute('/devices/new')({
  component: NewDeviceRoute,
  validateSearch: (search: Record<string, unknown>): NewDeviceSearch => ({
    config: typeof search.config === 'string' ? search.config : undefined,
    from: typeof search.from === 'string' ? search.from : undefined,
  }),
})

function NewDeviceRoute() {
  const { config, from } = Route.useSearch()

  // Parse config from search params if present (for duplicate flow)
  let initialConfig: Record<string, unknown> | undefined
  if (config) {
    try {
      initialConfig = JSON.parse(config)
    } catch {
      // Invalid JSON, ignore
    }
  }

  return (
    <div className="flex h-full flex-col">
      <DeviceEditor
        mode="new"
        initialConfig={initialConfig}
        duplicateFrom={from}
      />
    </div>
  )
}
