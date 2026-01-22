import { useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { DeviceConfig } from '@/hooks/use-devices'
import type { SortPreference } from '@/lib/utils/sort-preferences'

interface DeviceListTableProps {
  devices: DeviceConfig[]
  isLoading: boolean
  sortPreference: SortPreference
  onSortChange: (column: SortPreference['column']) => void
  onDelete: (device: DeviceConfig) => void
}

export function DeviceListTable({
  devices,
  isLoading,
  sortPreference,
  onSortChange,
  onDelete
}: DeviceListTableProps) {
  const sortedDevices = useMemo(() => {
    const sorted = [...devices]
    sorted.sort((a, b) => {
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
    return sorted
  }, [devices, sortPreference])

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
        className="px-4 py-3 text-left text-sm font-semibold text-zinc-50 cursor-pointer hover:bg-zinc-800"
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
        <thead className="border-b border-zinc-800">
          <tr>
            {renderSortHeader('macAddress', 'MAC Address')}
            {renderSortHeader('deviceName', 'Device Name')}
            {renderSortHeader('deviceEntityId', 'Entity ID')}
            {renderSortHeader('enableOta', 'OTA Status')}
            <th className="px-4 py-3 text-right text-sm font-semibold text-zinc-50">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sortedDevices.map((device) => (
            <tr
              key={device.id}
              className="border-b border-zinc-800 hover:bg-zinc-900"
              data-testid="devices.list.row"
              data-device-id={device.id}
            >
              <td className="px-4 py-3 text-sm text-zinc-50 font-mono">{device.macAddress}</td>
              <td className="px-4 py-3 text-sm text-zinc-300">{device.deviceName || '—'}</td>
              <td className="px-4 py-3 text-sm text-zinc-300 font-mono">{device.deviceEntityId || '—'}</td>
              <td className="px-4 py-3 text-sm text-zinc-300">
                {device.enableOta === true && <span className="text-green-400">✓</span>}
                {device.enableOta === false && <span className="text-red-400">✕</span>}
                {device.enableOta === null && <span className="text-zinc-600">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                <div className="flex items-center justify-end gap-2">
                  <Link to="/devices/$deviceId" params={{ deviceId: String(device.id) }}>
                    <Button
                      variant="outline"
                      size="sm"
                      data-testid="devices.list.row.edit-button"
                      title="Edit device"
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => onDelete(device)}
                    data-testid="devices.list.row.delete-button"
                    title="Delete device"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
