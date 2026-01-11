import { createFileRoute, Link } from '@tanstack/react-router'
import { DeviceEditor } from '@/components/devices/device-editor'
import { useDevice } from '@/hooks/use-devices'
import { Button } from '@/components/ui/button'

export const Route = createFileRoute('/devices/$macAddress')({
  component: EditDeviceRoute,
})

function EditDeviceRoute() {
  const { macAddress } = Route.useParams()
  const { config, isLoading, error } = useDevice(macAddress)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-zinc-400">Loading device configuration...</p>
      </div>
    )
  }

  if (error || !config) {
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
      <DeviceEditor mode="edit" initialMacAddress={macAddress} initialConfig={config} />
    </div>
  )
}
