import { createFileRoute, Outlet } from '@tanstack/react-router'

export const Route = createFileRoute('/devices/$deviceId/coredumps')({
  component: CoredumpsLayout,
})

// Layout route for coredumps: needed because both index.tsx and $coredumpId.tsx exist as children
function CoredumpsLayout() {
  return <Outlet />
}
