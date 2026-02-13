import type { Device } from '@/hooks/use-devices'
import { EmptyState } from '@/components/ui/empty-state'
import { DeviceLogsViewer } from './device-logs-viewer'

interface DeviceLogsTabProps {
  device: Device
}

/**
 * Logs tab content. Shows an empty state when no entity ID is configured,
 * otherwise renders the log viewer filling the available height.
 */
export function DeviceLogsTab({ device }: DeviceLogsTabProps) {
  const hasEntityId = device.deviceEntityId && device.deviceEntityId.trim() !== ''

  if (!hasEntityId) {
    return (
      <div className="p-6">
        <EmptyState
          title="No entity ID configured"
          description="Logs require a device entity ID. Add one in the Configuration tab."
          data-testid="devices.logs.empty"
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full p-6" data-testid="devices.logs.tab">
      <DeviceLogsViewer
        deviceId={device.id}
        deviceEntityId={device.deviceEntityId}
        fullHeight
      />
    </div>
  )
}
