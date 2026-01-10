import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/devices/')({
  component: DeviceListPlaceholder,
})

function DeviceListPlaceholder() {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold text-zinc-50" data-testid="devices.list-placeholder">
        Device Configs
      </h1>
      <p className="mt-4 text-zinc-400">
        Device list will be implemented in Phase B.
      </p>
    </div>
  )
}
