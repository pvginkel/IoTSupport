import { createFileRoute, Link } from '@tanstack/react-router'
import { DeviceEditor } from '@/components/devices/device-editor'
import { useDevice } from '@/hooks/use-devices'
import { Button } from '@/components/ui/button'

export const Route = createFileRoute('/devices/$deviceId/duplicate')({
  component: DuplicateDeviceRoute,
})

function DuplicateDeviceRoute() {
  const { deviceId } = Route.useParams()
  const numericId = parseInt(deviceId, 10)
  const { device, config, isLoading, error } = useDevice(isNaN(numericId) ? undefined : numericId)

  if (isNaN(numericId)) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-red-400">Invalid device ID</p>
        <Link to="/devices">
          <Button variant="outline">Back to Device List</Button>
        </Link>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-zinc-400">Loading device configuration...</p>
      </div>
    )
  }

  if (error || !device || !config) {
    const errorMessage = error?.message || 'Device not found'
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-red-400">{errorMessage}</p>
        <Link to="/devices">
          <Button variant="outline">Back to Device List</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <DeviceEditor
        mode="duplicate"
        initialMacAddress={device.macAddress}
        initialConfig={config}
      />
    </div>
  )
}
