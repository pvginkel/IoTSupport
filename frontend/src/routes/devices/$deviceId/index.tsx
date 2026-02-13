import { createFileRoute } from '@tanstack/react-router'
import { DeviceConfigurationTab } from '@/components/devices/device-configuration-tab'
import { useDevice } from '@/hooks/use-devices'

export const Route = createFileRoute('/devices/$deviceId/')({
  component: ConfigurationTabRoute,
})

// Configuration tab: layout handles loading/error, so we just pull device from cache
function ConfigurationTabRoute() {
  const { deviceId } = Route.useParams()
  const numericId = parseInt(deviceId, 10)
  const { device } = useDevice(isNaN(numericId) ? undefined : numericId)

  // Device may be null briefly while cache populates — the layout
  // already handles loading/error, so we can return null to avoid flicker
  if (!device) {
    return null
  }

  return <DeviceConfigurationTab device={device} />
}
