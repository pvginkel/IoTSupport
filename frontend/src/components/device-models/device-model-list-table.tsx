import { useMemo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Trash2 } from 'lucide-react'
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
  const navigate = useNavigate()

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
        className="px-4 py-3 text-left text-sm font-semibold text-foreground cursor-pointer hover:bg-secondary"
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
        <thead className="border-b border-border">
          <tr>
            {renderSortHeader('code', 'Code')}
            {renderSortHeader('name', 'Name')}
            {renderSortHeader('deviceCount', 'Devices')}
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Schema</th>
            <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Firmware</th>
            <th className="px-4 py-3 text-right text-sm font-semibold text-foreground">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sortedModels.map((model) => (
            <tr
              key={model.id}
              className="border-b border-border hover:bg-secondary/50 cursor-pointer"
              data-testid="device-models.list.row"
              data-model-id={model.id}
              data-model-code={model.code}
              onClick={() => navigate({ to: '/device-models/$modelId', params: { modelId: String(model.id) } })}
            >
              <td className="px-4 py-3 text-sm text-foreground font-mono">{model.code}</td>
              <td className="px-4 py-3 text-sm text-muted-foreground">{model.name}</td>
              <td className="px-4 py-3 text-sm text-muted-foreground">{model.deviceCount}</td>
              <td className="px-4 py-3 text-sm text-muted-foreground">
                {model.hasConfigSchema ? (
                  <span className="text-green-400">Defined</span>
                ) : (
                  <span className="text-muted-foreground/50">None</span>
                )}
              </td>
              <td className="px-4 py-3 text-sm text-muted-foreground font-mono">
                {model.firmwareVersion || <span className="text-muted-foreground/50">—</span>}
              </td>
              <td className="px-4 py-3 text-right">
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(model)
                  }}
                  data-testid="device-models.list.row.delete-button"
                  title={model.deviceCount > 0 ? 'Cannot delete: model has devices' : 'Delete model'}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
