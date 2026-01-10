import { createFileRoute } from '@tanstack/react-router'
import { DeviceEditor } from '@/components/devices/device-editor'
import { useDevice } from '@/hooks/use-devices'

export const Route = createFileRoute('/devices/$macAddress')({
  component: EditDeviceRoute,
})

function EditDeviceRoute() {
  const { macAddress } = Route.useParams()
  const { config, isLoading } = useDevice(macAddress)

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-zinc-400">Loading device configuration...</p>
      </div>
    )
  }

  if (!config) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-red-400">Device not found</p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <DeviceEditor mode="edit" initialMacAddress={macAddress} initialConfig={config} />
    </div>
  )
}
