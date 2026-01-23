import { createFileRoute } from '@tanstack/react-router'
import { RotationDashboard } from '@/components/rotation/rotation-dashboard'

export const Route = createFileRoute('/rotation')({
  component: RotationRoute,
})

function RotationRoute() {
  return <RotationDashboard />
}
