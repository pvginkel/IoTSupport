import { createFileRoute } from '@tanstack/react-router'
import { DeviceModelEditor } from '@/components/device-models/device-model-editor'

export const Route = createFileRoute('/device-models/new')({
  component: NewDeviceModelRoute,
})

function NewDeviceModelRoute() {
  return (
    <div className="flex h-full flex-col">
      <DeviceModelEditor mode="new" />
    </div>
  )
}
