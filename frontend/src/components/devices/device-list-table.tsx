import { useMemo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Trash2 } from 'lucide-react'
import { Button } from '@/components/primitives/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { DeviceSummary } from '@/hooks/use-devices'
import type { DeviceModelSummary } from '@/hooks/use-device-models'
import type { SortPreference } from '@/lib/utils/sort-preferences'
import { getRotationStateBadge } from '@/lib/utils/device-badges'

// Extended device with model name for sorting
interface DeviceWithModelName extends DeviceSummary {
  modelName: string
}

interface DeviceListTableProps {
  devices: DeviceSummary[]
  deviceModels: DeviceModelSummary[]
  isLoading: boolean
  sortPreference: SortPreference
  onSortChange: (column: SortPreference['column']) => void
  onDelete: (device: DeviceSummary) => void
}

export function DeviceListTable({
  devices,
  deviceModels,
  isLoading,
  sortPreference,
  onSortChange,
  onDelete
}: DeviceListTableProps) {
  const navigate = useNavigate()

  // Create a map of model ID to model name for efficient lookup
  const modelNameMap = useMemo(() => {
    const map = new Map<number, string>()
    deviceModels.forEach(model => {
      map.set(model.id, model.name)
    })
    return map
  }, [deviceModels])

  // Enhance devices with model name and sort
  const sortedDevices = useMemo(() => {
    // First, add model names to devices
    const devicesWithNames: DeviceWithModelName[] = devices.map(device => ({
      ...device,
      modelName: modelNameMap.get(device.deviceModelId) ?? 'Unknown'
    }))

    // Then sort
    devicesWithNames.sort((a, b) => {
      const aVal = a[sortPreference.column]
      const bVal = b[sortPreference.column]

      // Handle null values
      if (aVal === null && bVal === null) return 0
      if (aVal === null) return sortPreference.direction === 'asc' ? 1 : -1
      if (bVal === null) return sortPreference.direction === 'asc' ? -1 : 1

      // Compare values
      const comparison = aVal < bVal ? -1 : aVal > bVal ? 1 : 0
      return sortPreference.direction === 'asc' ? comparison : -comparison
    })
    return devicesWithNames
  }, [devices, sortPreference, modelNameMap])

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="devices.list.loading">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  // Render sort header helper
  const renderSortHeader = (column: SortPreference['column'], children: React.ReactNode) => {
    const isActive = sortPreference.column === column
    return (
      <th
        key={column}
        className="px-4 py-3 text-left text-sm font-semibold text-foreground cursor-pointer hover:bg-secondary"
        onClick={() => onSortChange(column)}
        data-testid={`devices.list.header.${column}`}
      >
        <div className="flex items-center gap-2">
          {children}
          {isActive && (
            <span className="text-xs">{sortPreference.direction === 'asc' ? '↑' : '↓'}</span>
          )}
        </div>
      </th>
    )
  }

  return (
    <div className="overflow-x-auto" data-testid="devices.list.table">
      <table className="w-full border-collapse">
        <thead className="border-b border-border">
          <tr>
            {renderSortHeader('key', 'Device Key')}
            {renderSortHeader('deviceName', 'Device Name')}
            {renderSortHeader('modelName', 'Model')}
            {renderSortHeader('deviceEntityId', 'Entity ID')}
            {renderSortHeader('rotationState', 'Rotation State')}
            {renderSortHeader('enableOta', 'OTA Status')}
            {renderSortHeader('lastCoredumpAt', 'Last Core Dump')}
            <th className="px-4 py-3 text-right text-sm font-semibold text-foreground">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sortedDevices.map((device) => {
            const rotationBadge = getRotationStateBadge(device.rotationState)
            return (
              <tr
                key={device.id}
                className="border-b border-border hover:bg-secondary/50 cursor-pointer"
                data-testid="devices.list.row"
                data-device-id={device.id}
                data-device-key={device.key}
                data-rotation-state={device.rotationState}
                onClick={() => navigate({ to: '/devices/$deviceId', params: { deviceId: String(device.id) } })}
              >
                <td className="px-4 py-3 text-sm text-foreground font-mono">{device.key}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground">{device.deviceName || '—'}</td>
                <td className="px-4 py-3 text-sm text-muted-foreground" data-testid="devices.list.row.model">
                  {device.modelName}
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground font-mono">{device.deviceEntityId || '—'}</td>
                <td className="px-4 py-3 text-sm" data-testid="devices.list.row.rotation-state">
                  <span className={`px-2 py-1 rounded-md text-xs ${rotationBadge.bgColor} ${rotationBadge.textColor}`}>
                    {device.rotationState}
                  </span>
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {device.enableOta === true && <span className="text-green-400">✓</span>}
                  {device.enableOta === false && <span className="text-red-400">✕</span>}
                  {device.enableOta === null && <span className="text-muted-foreground/50">—</span>}
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {device.lastCoredumpAt
                    ? new Date(device.lastCoredumpAt).toLocaleString()
                    : '—'}
                </td>
                <td className="px-4 py-3 text-right">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDelete(device)
                    }}
                    data-testid="devices.list.row.delete-button"
                    title="Delete device"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
