import { createFileRoute } from '@tanstack/react-router'
import { CoredumpAccordionTable } from '@/components/devices/coredump-accordion-table'
import { useDevice } from '@/hooks/use-devices'

export const Route = createFileRoute('/devices/$deviceId/coredumps/$coredumpId')({
  component: CoredumpExpandedRoute,
})

function CoredumpExpandedRoute() {
  const { deviceId, coredumpId } = Route.useParams()
  const numericDeviceId = parseInt(deviceId, 10)
  const numericCoredumpId = parseInt(coredumpId, 10)
  const { device } = useDevice(isNaN(numericDeviceId) ? undefined : numericDeviceId)

  if (!device || isNaN(numericCoredumpId)) {
    return null
  }

  return (
    <CoredumpAccordionTable
      deviceId={device.id}
      expandedCoredumpId={numericCoredumpId}
    />
  )
}
