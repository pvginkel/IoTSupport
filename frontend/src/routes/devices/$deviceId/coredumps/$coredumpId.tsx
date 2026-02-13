import { createFileRoute, Link } from '@tanstack/react-router'
import { useCoredump } from '@/hooks/use-coredumps'
import { CoredumpDetail } from '@/components/devices/coredump-detail'
import { Button } from '@/components/ui/button'

export const Route = createFileRoute('/devices/$deviceId/coredumps/$coredumpId')({
  component: CoredumpDetailRoute,
})

function CoredumpDetailRoute() {
  const { deviceId, coredumpId } = Route.useParams()
  const numericDeviceId = parseInt(deviceId, 10)
  const numericCoredumpId = parseInt(coredumpId, 10)

  const validIds = !isNaN(numericDeviceId) && !isNaN(numericCoredumpId)
  const { coredump, isLoading, error } = useCoredump(
    validIds ? numericDeviceId : undefined,
    validIds ? numericCoredumpId : undefined
  )

  // Invalid IDs
  if (!validIds) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-destructive">Invalid device or core dump ID</p>
        <Link to="/devices">
          <Button variant="outline">Back to Device List</Button>
        </Link>
      </div>
    )
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading core dump...</p>
      </div>
    )
  }

  // Error or not found
  if (error || !coredump) {
    const errorMessage = error?.message || 'Core dump not found'
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4" data-testid="coredumps.detail.error">
        <p className="text-destructive">{errorMessage}</p>
        <Link to="/devices/$deviceId" params={{ deviceId }}>
          <Button variant="outline">Back to Device</Button>
        </Link>
      </div>
    )
  }

  return (
    <CoredumpDetail
      coredump={coredump}
      deviceId={deviceId}
    />
  )
}
