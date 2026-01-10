import { createFileRoute } from '@tanstack/react-router'
import { DeviceEditor } from '@/components/devices/device-editor'

export const Route = createFileRoute('/devices/new')({
  component: NewDeviceRoute,
})

function NewDeviceRoute() {
  return (
    <div className="flex h-full flex-col">
      <DeviceEditor mode="new" />
    </div>
  )
}
