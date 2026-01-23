import { useMemo, useCallback } from 'react'
import { Link } from '@tanstack/react-router'
import { useRotationDashboard, useRotationStatus, useTriggerRotation, type RotationDashboardDevice } from '@/hooks/use-rotation'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/ui/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'
import { RefreshCw, AlertCircle, CheckCircle, Clock, XCircle, ExternalLink } from 'lucide-react'

// Helper to format dates
function formatDate(dateString: string | null): string {
  if (!dateString) return '—'
  return new Date(dateString).toLocaleString()
}

// Helper to get status badge styling
function getStatusBadge(state: string): { color: string; icon: React.ReactNode } {
  switch (state.toUpperCase()) {
    case 'OK':
      return { color: 'text-green-400', icon: <CheckCircle className="h-4 w-4" /> }
    case 'PENDING':
    case 'QUEUED':
      return { color: 'text-yellow-400', icon: <Clock className="h-4 w-4" /> }
    case 'TIMEOUT':
      return { color: 'text-red-400', icon: <XCircle className="h-4 w-4" /> }
    case 'ROTATING':
      return { color: 'text-blue-400', icon: <RefreshCw className="h-4 w-4 animate-spin" /> }
    default:
      return { color: 'text-zinc-400', icon: <AlertCircle className="h-4 w-4" /> }
  }
}

// Helper to get category badge styling
function getCategoryColor(category: string): string {
  switch (category) {
    case 'healthy':
      return 'bg-green-900/20 text-green-400 border-green-800'
    case 'warning':
      return 'bg-yellow-900/20 text-yellow-400 border-yellow-800'
    case 'critical':
      return 'bg-red-900/20 text-red-400 border-red-800'
    default:
      return 'bg-zinc-800 text-zinc-400 border-zinc-700'
  }
}

// Helper to get days badge styling
function getDaysColor(days: number | null): string {
  if (days === null) return 'text-zinc-500'
  if (days > 90) return 'text-red-400'
  if (days > 60) return 'text-yellow-400'
  return 'text-green-400'
}

export function RotationDashboard() {
  const { devices, counts, isLoading: devicesLoading, isFetching: devicesFetching, error: devicesError } = useRotationDashboard()
  const { status, isLoading: statusLoading, error: statusError } = useRotationStatus()
  const triggerRotation = useTriggerRotation()
  const { confirm, confirmProps } = useConfirm()

  // Instrumentation for Playwright
  useListLoadingInstrumentation({
    scope: 'rotation.dashboard',
    isLoading: devicesLoading,
    isFetching: devicesFetching,
    error: devicesError,
    getReadyMetadata: () => ({ visible: devices.length, total: devices.length })
  })

  // Count devices by state from status API
  const stateOkCount = useMemo(() => {
    return status?.countsByState?.OK ?? 0
  }, [status])

  const handleTriggerRotation = useCallback(async () => {
    if (stateOkCount === 0) {
      await confirm({
        title: 'No Devices to Rotate',
        description: 'There are no devices in OK state ready for rotation.',
        confirmText: 'OK',
        cancelText: ''
      })
      return
    }

    const confirmed = await confirm({
      title: 'Trigger Fleet Rotation',
      description: `This will queue ${stateOkCount} device${stateOkCount > 1 ? 's' : ''} for credential rotation. Devices will rotate one at a time. Continue?`,
      confirmText: 'Trigger Rotation',
      destructive: false
    })

    if (confirmed) {
      triggerRotation.mutate()
    }
  }, [confirm, stateOkCount, triggerRotation])

  const isLoading = devicesLoading || statusLoading
  const error = devicesError || statusError

  if (error) {
    return (
      <div className="p-8" data-testid="rotation.dashboard.error">
        <h1 className="text-2xl font-bold text-zinc-50">Rotation Dashboard</h1>
        <p className="mt-4 text-red-400">Failed to load rotation data: {error.message}</p>
      </div>
    )
  }

  return (
    <div className="p-8" data-testid="rotation.dashboard">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-zinc-50">Rotation Dashboard</h1>
        <Button
          variant="primary"
          onClick={handleTriggerRotation}
          disabled={triggerRotation.isPending || isLoading}
          loading={triggerRotation.isPending}
          data-testid="rotation.dashboard.trigger-button"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Trigger Fleet Rotation
        </Button>
      </div>

      {/* Status Summary Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8" data-testid="rotation.dashboard.summary">
          <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
            <div className="text-zinc-400 text-sm">Healthy</div>
            <div className="text-2xl font-bold text-green-400" data-testid="rotation.dashboard.count.healthy">
              {counts.healthy ?? 0}
            </div>
          </div>
          <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
            <div className="text-zinc-400 text-sm">Warning</div>
            <div className="text-2xl font-bold text-yellow-400" data-testid="rotation.dashboard.count.warning">
              {counts.warning ?? 0}
            </div>
          </div>
          <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
            <div className="text-zinc-400 text-sm">Critical</div>
            <div className="text-2xl font-bold text-red-400" data-testid="rotation.dashboard.count.critical">
              {counts.critical ?? 0}
            </div>
          </div>
          <div className="bg-zinc-900 rounded-lg p-4 border border-zinc-800">
            <div className="text-zinc-400 text-sm">Total</div>
            <div className="text-2xl font-bold text-zinc-50" data-testid="rotation.dashboard.count.total">
              {devices.length}
            </div>
          </div>
        </div>
      )}

      {/* Schedule Info */}
      {status && (
        <div className="mb-8 bg-zinc-900 rounded-lg p-4 border border-zinc-800" data-testid="rotation.dashboard.schedule">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-zinc-400 text-sm">Last Rotation Completed</div>
              <div className="text-zinc-50">{formatDate(status.lastRotationCompletedAt)}</div>
            </div>
            <div>
              <div className="text-zinc-400 text-sm">Next Scheduled Rotation</div>
              <div className="text-zinc-50">{formatDate(status.nextScheduledRotation)}</div>
            </div>
            <div>
              <div className="text-zinc-400 text-sm">Currently Pending</div>
              {status.pendingDeviceId ? (
                <Link
                  to="/devices/$deviceId"
                  params={{ deviceId: String(status.pendingDeviceId) }}
                  className="inline-flex items-center gap-1 text-blue-400 hover:text-blue-300"
                  data-testid="rotation.dashboard.pending-device-link"
                >
                  View Device
                  <ExternalLink className="h-3 w-3" />
                </Link>
              ) : (
                <div className="text-zinc-50" data-testid="rotation.dashboard.no-pending">
                  None
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Devices Table */}
      {isLoading ? (
        <div className="space-y-2" data-testid="rotation.dashboard.loading">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : devices.length === 0 ? (
        <div className="text-center py-12 text-zinc-400" data-testid="rotation.dashboard.empty">
          No devices found
        </div>
      ) : (
        <div className="overflow-x-auto" data-testid="rotation.dashboard.table">
          <table className="w-full border-collapse">
            <thead className="border-b border-zinc-800">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Device Key</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Model</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Category</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">State</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Secret Age</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-zinc-50">Last Rotation</th>
              </tr>
            </thead>
            <tbody>
              {devices.map((device: RotationDashboardDevice) => {
                const statusBadge = getStatusBadge(device.rotationState)
                return (
                  <tr
                    key={device.id}
                    className="border-b border-zinc-800 hover:bg-zinc-900"
                    data-testid="rotation.dashboard.row"
                    data-device-id={device.id}
                    data-rotation-state={device.rotationState}
                    data-category={device.category}
                  >
                    <td className="px-4 py-3 text-sm text-zinc-50 font-mono">{device.key}</td>
                    <td className="px-4 py-3 text-sm text-zinc-300">
                      {device.deviceModelCode}
                      {device.deviceName && (
                        <span className="text-zinc-500 ml-2">({device.deviceName})</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`px-2 py-1 rounded-md text-xs border ${getCategoryColor(device.category)}`}>
                        {device.category.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <span className={`flex items-center gap-1 ${statusBadge.color}`}>
                        {statusBadge.icon}
                        {device.rotationState}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-sm ${getDaysColor(device.daysSinceRotation)}`}>
                      {device.daysSinceRotation !== null ? `${device.daysSinceRotation} days` : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-zinc-300">
                      {formatDate(device.lastRotationCompletedAt)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <ConfirmDialog {...confirmProps} contentProps={{ 'data-testid': 'rotation.dashboard.confirm-dialog' }} />
    </div>
  )
}
