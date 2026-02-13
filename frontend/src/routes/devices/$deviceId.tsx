import { createFileRoute, Outlet } from '@tanstack/react-router'

export const Route = createFileRoute('/devices/$deviceId')({
  component: DeviceIdLayout,
})

// Layout route: renders child routes (index, duplicate, coredump detail)
function DeviceIdLayout() {
  return <Outlet />
}
