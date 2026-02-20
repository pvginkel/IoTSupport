import { useState, useCallback } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useDeviceModels, useDeleteDeviceModel, type DeviceModelSummary } from '@/hooks/use-device-models'
import { DeviceModelListTable } from '@/components/device-models/device-model-list-table'
import { Button } from '@/components/primitives/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ConfirmDialog } from '@/components/primitives/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'

export const Route = createFileRoute('/device-models/')({
  component: DeviceModelList,
})

// Sort state for device models
type SortColumn = 'code' | 'name' | 'deviceCount'
interface SortPreference {
  column: SortColumn
  direction: 'asc' | 'desc'
}

function DeviceModelList() {
  const { deviceModels, isLoading, isFetching, error } = useDeviceModels()
  const deleteDeviceModel = useDeleteDeviceModel()
  const { confirm, confirmProps } = useConfirm()

  const [sortPreference, setSortPreference] = useState<SortPreference>({
    column: 'name',
    direction: 'asc'
  })

  // List loading instrumentation for Playwright
  useListLoadingInstrumentation({
    scope: 'device-models.list',
    isLoading,
    isFetching,
    error,
    getReadyMetadata: () => ({ visible: deviceModels.length, total: deviceModels.length })
  })

  const handleSortChange = useCallback((column: SortColumn) => {
    setSortPreference((prev) => ({
      column,
      direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc'
    }))
  }, [])

  const handleDelete = useCallback(async (model: DeviceModelSummary) => {
    if (model.deviceCount > 0) {
      await confirm({
        title: 'Cannot Delete Model',
        description: `This model has ${model.deviceCount} device${model.deviceCount > 1 ? 's' : ''} using it. Remove all devices first before deleting the model.`,
        confirmText: 'OK',
        cancelText: 'Cancel'
      })
      return
    }

    const confirmed = await confirm({
      title: 'Delete Device Model',
      description: `Delete device model "${model.name}" (${model.code})? This action cannot be undone.`,
      confirmText: 'Delete',
      destructive: true
    })

    if (confirmed) {
      deleteDeviceModel.mutate({ id: model.id })
    }
  }, [confirm, deleteDeviceModel])

  if (error) {
    return (
      <div className="p-8" data-testid="device-models.list.error">
        <h1 className="text-2xl font-bold text-foreground">Device Models</h1>
        <p className="mt-4 text-destructive">Failed to load device models: {error.message}</p>
      </div>
    )
  }

  if (!isLoading && deviceModels.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-foreground">Device Models</h1>
          <Link to="/device-models/new">
            <Button variant="primary" data-testid="device-models.list.header.new-model">
              New Model
            </Button>
          </Link>
        </div>
        <EmptyState
          title="No device models defined"
          description="Get started by creating your first device model. Models define configuration schemas for devices."
          action={
            <Link to="/device-models/new">
              <Button variant="primary">Create Device Model</Button>
            </Link>
          }
          data-testid="device-models.list.empty"
        />
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Device Models</h1>
        <Link to="/device-models/new">
          <Button variant="primary" data-testid="device-models.list.header.new-model">
            New Model
          </Button>
        </Link>
      </div>

      <DeviceModelListTable
        deviceModels={deviceModels}
        isLoading={isLoading}
        sortPreference={sortPreference}
        onSortChange={handleSortChange}
        onDelete={handleDelete}
      />

      <ConfirmDialog {...confirmProps} contentProps={{ 'data-testid': 'device-models.delete.confirm-dialog' }} />
    </div>
  )
}
