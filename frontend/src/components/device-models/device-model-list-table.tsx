import { useMemo } from 'react'
import { Link } from '@tanstack/react-router'
import { Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import type { DeviceModelSummary } from '@/hooks/use-device-models'

type SortColumn = 'code' | 'name' | 'deviceCount'
interface SortPreference {
  column: SortColumn
  direction: 'asc' | 'desc'
}

interface DeviceModelListTableProps {
  deviceModels: DeviceModelSummary[]
  isLoading: boolean
  sortPreference: SortPreference
  onSortChange: (column: SortColumn) => void
  onDelete: (model: DeviceModelSummary) => void
}

export function DeviceModelListTable({
  deviceModels,
  isLoading,
  sortPreference,
  onSortChange,
  onDelete
}: DeviceModelListTableProps) {
  const sortedModels = useMemo(() => {
    const sorted = [...deviceModels]
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
  }, [deviceModels, sortPreference])

  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="device-models.list.loading">
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  // Render sort header helper
  const renderSortHeader = (column: SortColumn, children: React.ReactNode) => {
    const isActive = sortPreference.column === column
    return (
      <th
        key={column}
        className="px-4 py-3 text-left text-sm font-semibold text-zinc-50 cursor-pointer hover:bg-zinc-800"
        onClick={() => onSortChange(column)}
        data-testid={`device-models.list.header.${column}`}
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
    <div className="overflow-x-auto" data-testid="device-models.list.table">
      <table className="w-full border-collapse">
        <thead className="border-b border-zinc-800">
          <tr>
            {renderSortHeader('code', 'Code')}
            {renderSortHeader('name', 'Name')}
            {renderSortHeader('deviceCount', 'Devices')}
            <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Schema</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Firmware</th>
            <th className="px-4 py-3 text-right text-sm font-semibold text-zinc-50">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sortedModels.map((model) => (
            <tr
              key={model.id}
              className="border-b border-zinc-800 hover:bg-zinc-900"
              data-testid="device-models.list.row"
              data-model-id={model.id}
              data-model-code={model.code}
            >
              <td className="px-4 py-3 text-sm text-zinc-50 font-mono">{model.code}</td>
              <td className="px-4 py-3 text-sm text-zinc-300">{model.name}</td>
              <td className="px-4 py-3 text-sm text-zinc-300">{model.deviceCount}</td>
              <td className="px-4 py-3 text-sm text-zinc-300">
                {model.hasConfigSchema ? (
                  <span className="text-green-400">Defined</span>
                ) : (
                  <span className="text-zinc-600">None</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-zinc-300 font-mono">
                {model.firmwareVersion || <span className="text-zinc-600">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                <div className="flex items-center justify-end gap-2">
                  <Link to="/device-models/$modelId" params={{ modelId: String(model.id) }}>
                    <Button
                      variant="outline"
                      size="sm"
                      data-testid="device-models.list.row.edit-button"
                      title="Edit model"
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => onDelete(model)}
                    data-testid="device-models.list.row.delete-button"
                    title={model.deviceCount > 0 ? 'Cannot delete: model has devices' : 'Delete model'}
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
