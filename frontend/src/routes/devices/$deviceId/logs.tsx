import { createFileRoute } from '@tanstack/react-router'
import { DeviceLogsTab } from '@/components/devices/device-logs-tab'
import { useDevice } from '@/hooks/use-devices'

export const Route = createFileRoute('/devices/$deviceId/logs')({
  component: LogsTabRoute,
})

function LogsTabRoute() {
  const { deviceId } = Route.useParams()
  const numericId = parseInt(deviceId, 10)
  const { device } = useDevice(isNaN(numericId) ? undefined : numericId)

  if (!device) {
    return null
  }

  return <DeviceLogsTab device={device} />
}
