import { createFileRoute, redirect } from '@tanstack/react-router'
import { DeviceConfigurationTab } from '@/components/devices/device-configuration-tab'
import { useDevice } from '@/hooks/use-devices'
import { getDeviceTabPreference } from '@/lib/utils/device-tab-preference'

export const Route = createFileRoute('/devices/$deviceId/')({
  beforeLoad: ({ params }) => {
    const tab = getDeviceTabPreference()
    if (tab === 'logs') {
      throw redirect({ to: '/devices/$deviceId/logs', params })
    }
    if (tab === 'coredumps') {
      throw redirect({ to: '/devices/$deviceId/coredumps', params })
    }
  },
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
