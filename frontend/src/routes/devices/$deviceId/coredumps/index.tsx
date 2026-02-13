import { createFileRoute } from '@tanstack/react-router'
import { CoredumpAccordionTable } from '@/components/devices/coredump-accordion-table'
import { useDevice } from '@/hooks/use-devices'

export const Route = createFileRoute('/devices/$deviceId/coredumps/')({
  component: CoredumpsIndexRoute,
})

function CoredumpsIndexRoute() {
  const { deviceId } = Route.useParams()
  const numericId = parseInt(deviceId, 10)
  const { device } = useDevice(isNaN(numericId) ? undefined : numericId)

  if (!device) {
    return null
  }

  return <CoredumpAccordionTable deviceId={device.id} />
}
