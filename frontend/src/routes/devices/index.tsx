import { useState, useCallback } from 'react'
import { createFileRoute, Link } from '@tanstack/react-router'
import { useDevices, useDeleteDevice, type DeviceSummary } from '@/hooks/use-devices'
import { useDeviceModels } from '@/hooks/use-device-models'
import { DeviceListTable } from '@/components/devices/device-list-table'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { ConfirmDialog } from '@/components/ui/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { getSortPreference, setSortPreference, type SortPreference } from '@/lib/utils/sort-preferences'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'

export const Route = createFileRoute('/devices/')({
  component: DeviceList,
})

function DeviceList() {
  const { devices, isLoading, isFetching, error } = useDevices()
  const { deviceModels } = useDeviceModels()
  const deleteDevice = useDeleteDevice()
  const { confirm, confirmProps } = useConfirm()

  const [sortPreference, setSortPreferenceState] = useState<SortPreference>(() => getSortPreference())

  // List loading instrumentation for Playwright
  useListLoadingInstrumentation({
    scope: 'devices.list',
    isLoading,
    isFetching,
    error,
    getReadyMetadata: () => ({ visible: devices.length, total: devices.length })
  })

  const handleSortChange = useCallback((column: SortPreference['column']) => {
    setSortPreferenceState((prev) => {
      const newPreference: SortPreference = {
        column,
        direction: prev.column === column && prev.direction === 'asc' ? 'desc' : 'asc'
      }
      setSortPreference(newPreference)
      return newPreference
    })
  }, [])

  const handleDelete = useCallback(async (device: DeviceSummary) => {
    const confirmed = await confirm({
      title: 'Delete Device',
      description: `Delete device ${device.key}? This action cannot be undone.`,
      confirmText: 'Delete',
      destructive: true
    })

    if (confirmed) {
      deleteDevice.mutate({ id: device.id })
    }
  }, [confirm, deleteDevice])

  if (error) {
    return (
      <div className="p-8" data-testid="devices.list.error">
        <h1 className="text-2xl font-bold text-zinc-50">Devices</h1>
        <p className="mt-4 text-red-400">Failed to load devices: {error.message}</p>
      </div>
    )
  }

  if (!isLoading && devices.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-bold text-zinc-50">Devices</h1>
          <Link to="/devices/new">
            <Button variant="primary" data-testid="devices.list.header.new-device">
              New Device
            </Button>
          </Link>
        </div>
        <EmptyState
          title="No devices configured"
          description="Get started by creating your first device configuration."
          action={
            <Link to="/devices/new">
              <Button variant="primary">Create Device</Button>
            </Link>
          }
          data-testid="devices.list.empty"
        />
      </div>
    )
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-zinc-50">Devices</h1>
        <Link to="/devices/new">
          <Button variant="primary" data-testid="devices.list.header.new-device">
            New Device
          </Button>
        </Link>
      </div>

      <DeviceListTable
        devices={devices}
        deviceModels={deviceModels}
        isLoading={isLoading}
        sortPreference={sortPreference}
        onSortChange={handleSortChange}
        onDelete={handleDelete}
      />

      <ConfirmDialog {...confirmProps} contentProps={{ 'data-testid': 'devices.delete.confirm-dialog' }} />
    </div>
  )
}
