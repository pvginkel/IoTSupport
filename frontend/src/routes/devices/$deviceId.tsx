import { createFileRoute, Outlet, Link, useMatches } from '@tanstack/react-router'
import { useDevice } from '@/hooks/use-devices'
import { DeviceDetailHeader } from '@/components/devices/device-detail-header'
import { Button } from '@/components/primitives/button'

export const Route = createFileRoute('/devices/$deviceId')({
  component: DeviceIdLayout,
})

// Layout route: fetches device, renders header + tabs + child route
function DeviceIdLayout() {
  const { deviceId } = Route.useParams()
  const numericId = parseInt(deviceId, 10)
  const { device, isLoading, error } = useDevice(isNaN(numericId) ? undefined : numericId)

  // Detect if we're in duplicate mode — if so, skip header/tabs
  const matches = useMatches()
  const isDuplicate = matches.some(m => m.fullPath.endsWith('/duplicate'))

  // For duplicate route, render bare Outlet (no header/tabs)
  if (isDuplicate) {
    return <Outlet />
  }

  // Invalid device ID
  if (isNaN(numericId)) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-destructive">Invalid device ID</p>
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
        <p className="text-muted-foreground">Loading device...</p>
      </div>
    )
  }

  // Error / not found
  if (error || !device) {
    const errorMessage = error?.message || 'Device not found'
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-destructive">{errorMessage}</p>
        <Link to="/devices">
          <Button variant="outline">Back to Device List</Button>
        </Link>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <DeviceDetailHeader device={device} />
      <div className="flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
