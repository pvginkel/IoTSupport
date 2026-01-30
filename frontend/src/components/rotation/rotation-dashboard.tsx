import { useState, useMemo, useCallback, useEffect } from 'react'
import { Link } from '@tanstack/react-router'
import { useRotationDashboard, useRotationStatus, useTriggerRotation, type RotationDashboardDevice } from '@/hooks/use-rotation'
import { useDeviceModels } from '@/hooks/use-device-models'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/ui/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'
import { RefreshCw, ExternalLink, ChevronDown, ChevronRight, CheckCircle, Clock, XCircle, AlertCircle } from 'lucide-react'

// Helper to get status icon
function getStatusIcon(state: string): React.ReactNode {
  switch (state.toUpperCase()) {
    case 'OK':
      return <CheckCircle className="h-4 w-4" />
    case 'PENDING':
    case 'QUEUED':
      return <Clock className="h-4 w-4" />
    case 'TIMEOUT':
      return <XCircle className="h-4 w-4" />
    case 'ROTATING':
      return <RefreshCw className="h-4 w-4 animate-spin" />
    default:
      return <AlertCircle className="h-4 w-4" />
  }
}

const PANEL_STATE_STORAGE_KEY = 'rotation-dashboard-panels'

// Helper to format dates
function formatDate(dateString: string | null): string {
  if (!dateString) return '—'
  return new Date(dateString).toLocaleString()
}

// Category panel styling - bright outer frame, dark inner content
const categoryStyles = {
  healthy: {
    outerBg: 'bg-green-600',
    headerText: 'text-green-950',
    innerBg: 'bg-green-950/80',
    innerText: 'text-green-400',
    innerBorder: 'border-green-800',
    label: 'Healthy'
  },
  warning: {
    outerBg: 'bg-yellow-500',
    headerText: 'text-yellow-950',
    innerBg: 'bg-yellow-950/80',
    innerText: 'text-yellow-400',
    innerBorder: 'border-yellow-800',
    label: 'Warning'
  },
  critical: {
    outerBg: 'bg-red-600',
    headerText: 'text-red-950',
    innerBg: 'bg-red-950/80',
    innerText: 'text-red-400',
    innerBorder: 'border-red-800',
    label: 'Critical'
  }
} as const

type Category = keyof typeof categoryStyles

interface PanelState {
  healthy: boolean
  warning: boolean
  critical: boolean
}

// Load panel state from localStorage
function loadPanelState(): PanelState {
  try {
    const stored = localStorage.getItem(PANEL_STATE_STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch {
    // Ignore parse errors
  }
  // Default: all expanded
  return { healthy: true, warning: true, critical: true }
}

// Save panel state to localStorage
function savePanelState(state: PanelState): void {
  try {
    localStorage.setItem(PANEL_STATE_STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Ignore storage errors
  }
}

// Device table for a category panel
interface DeviceTableProps {
  devices: RotationDashboardDevice[]
  textColor: string
  modelNameMap: Map<string, string>
}

function DeviceTable({ devices, textColor, modelNameMap }: DeviceTableProps) {
  if (devices.length === 0) {
    return (
      <div className={`text-center py-6 ${textColor} opacity-70`}>
        No devices in this category
      </div>
    )
  }

  return (
    <table className="w-full border-collapse">
      <thead className="border-b border-border">
        <tr>
          <th className={`px-4 py-2 text-left text-sm font-semibold ${textColor} whitespace-nowrap`}>Device Key</th>
          <th className={`px-4 py-2 text-left text-sm font-semibold ${textColor}`} style={{ width: '25%' }}>Device Name</th>
          <th className={`px-4 py-2 text-left text-sm font-semibold ${textColor}`} style={{ width: '25%' }}>Model</th>
          <th className={`px-4 py-2 text-left text-sm font-semibold ${textColor} whitespace-nowrap`}>State</th>
          <th className={`px-4 py-2 text-left text-sm font-semibold ${textColor} whitespace-nowrap`}>Secret Age</th>
          <th className={`px-4 py-2 text-left text-sm font-semibold ${textColor} whitespace-nowrap`}>Last Rotation</th>
        </tr>
      </thead>
      <tbody>
        {devices.map((device) => {
          const modelName = modelNameMap.get(device.deviceModelCode) ?? device.deviceModelCode
          return (
            <tr
              key={device.id}
              className="border-b border-border/50 hover:bg-secondary/30"
              data-testid="rotation.dashboard.row"
              data-device-id={device.id}
              data-rotation-state={device.rotationState}
              data-category={device.category}
            >
              <td className={`px-4 py-2 text-sm font-mono ${textColor} whitespace-nowrap`}>{device.key}</td>
              <td className={`px-4 py-2 text-sm ${textColor} opacity-90 truncate max-w-0`}>
                {device.deviceName || '—'}
              </td>
              <td className={`px-4 py-2 text-sm ${textColor} opacity-90 truncate max-w-0`}>
                {modelName}
              </td>
              <td className={`px-4 py-2 text-sm ${textColor} opacity-90 whitespace-nowrap`}>
                <span className="flex items-center gap-1">
                  {getStatusIcon(device.rotationState)}
                  {device.rotationState}
                </span>
              </td>
              <td className={`px-4 py-2 text-sm ${textColor} opacity-90 whitespace-nowrap`}>
                {device.daysSinceRotation !== null ? `${device.daysSinceRotation} days` : '—'}
              </td>
              <td className={`px-4 py-2 text-sm ${textColor} opacity-90 whitespace-nowrap`}>
                {formatDate(device.lastRotationCompletedAt)}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

// Collapsible category panel
interface CategoryPanelProps {
  category: Category
  devices: RotationDashboardDevice[]
  isExpanded: boolean
  onToggle: () => void
  modelNameMap: Map<string, string>
}

function CategoryPanel({ category, devices, isExpanded, onToggle, modelNameMap }: CategoryPanelProps) {
  const style = categoryStyles[category]
  const count = devices.length

  return (
    <div
      className={`rounded-lg ${style.outerBg} p-1 overflow-hidden`}
      data-testid={`rotation.dashboard.panel.${category}`}
      data-expanded={isExpanded}
    >
      {/* Bright header */}
      <button
        onClick={onToggle}
        className={`w-full px-4 py-3 flex items-center justify-between rounded-t-md hover:brightness-110 transition-all cursor-pointer`}
        data-testid={`rotation.dashboard.panel.${category}.header`}
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className={`h-5 w-5 ${style.headerText}`} />
          ) : (
            <ChevronRight className={`h-5 w-5 ${style.headerText}`} />
          )}
          <span className={`font-semibold ${style.headerText}`}>{style.label}</span>
        </div>
        <span className={`text-lg font-bold ${style.headerText}`} data-testid={`rotation.dashboard.panel.${category}.count`}>
          {count} device{count !== 1 ? 's' : ''}
        </span>
      </button>
      {/* Dark inner content panel */}
      {isExpanded && (
        <div className={`rounded-md ${style.innerBg} p-3 m-1`}>
          <DeviceTable devices={devices} textColor={style.innerText} modelNameMap={modelNameMap} />
        </div>
      )}
    </div>
  )
}

// Horizontal stacked bar chart
interface StackedBarProps {
  healthy: number
  warning: number
  critical: number
}

function StackedBar({ healthy, warning, critical }: StackedBarProps) {
  const total = healthy + warning + critical

  if (total === 0) {
    return (
      <div className="h-10 bg-muted rounded-lg flex items-center justify-center text-muted-foreground text-sm">
        No devices
      </div>
    )
  }

  const healthyPct = (healthy / total) * 100
  const warningPct = (warning / total) * 100
  const criticalPct = (critical / total) * 100

  return (
    <div className="h-10 flex rounded-lg overflow-hidden" data-testid="rotation.dashboard.bar">
      {healthy > 0 && (
        <div
          className="bg-green-600 flex items-center justify-center text-green-950 text-lg font-bold transition-all"
          style={{ width: `${healthyPct}%` }}
          title={`Healthy: ${healthy}`}
          data-testid="rotation.dashboard.bar.healthy"
        >
          {healthy}
        </div>
      )}
      {warning > 0 && (
        <div
          className="bg-yellow-500 flex items-center justify-center text-yellow-950 text-lg font-bold transition-all"
          style={{ width: `${warningPct}%` }}
          title={`Warning: ${warning}`}
          data-testid="rotation.dashboard.bar.warning"
        >
          {warning}
        </div>
      )}
      {critical > 0 && (
        <div
          className="bg-red-600 flex items-center justify-center text-red-950 text-lg font-bold transition-all"
          style={{ width: `${criticalPct}%` }}
          title={`Critical: ${critical}`}
          data-testid="rotation.dashboard.bar.critical"
        >
          {critical}
        </div>
      )}
    </div>
  )
}

export function RotationDashboard() {
  const { healthy, warning, critical, counts, isLoading: devicesLoading, isFetching: devicesFetching, error: devicesError } = useRotationDashboard()
  const { status, isLoading: statusLoading, error: statusError } = useRotationStatus()
  const { deviceModels } = useDeviceModels()
  const triggerRotation = useTriggerRotation()
  const { confirm, confirmProps } = useConfirm()

  // Map device model code to name for display
  const modelNameMap = useMemo(() => {
    const map = new Map<string, string>()
    deviceModels.forEach(model => {
      map.set(model.code, model.name)
    })
    return map
  }, [deviceModels])

  // Panel expanded state (persisted to localStorage)
  const [panelState, setPanelState] = useState<PanelState>(loadPanelState)

  // Save panel state when it changes
  useEffect(() => {
    savePanelState(panelState)
  }, [panelState])

  const togglePanel = useCallback((category: Category) => {
    setPanelState(prev => ({
      ...prev,
      [category]: !prev[category]
    }))
  }, [])

  // Combine all devices for instrumentation
  const allDevices = useMemo(() => [...healthy, ...warning, ...critical], [healthy, warning, critical])

  // Instrumentation for Playwright
  useListLoadingInstrumentation({
    scope: 'rotation.dashboard',
    isLoading: devicesLoading,
    isFetching: devicesFetching,
    error: devicesError,
    getReadyMetadata: () => ({ visible: allDevices.length, total: allDevices.length })
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
      description: `This will queue ${stateOkCount} device${stateOkCount > 1 ? 's' : ''} for credential rotation. Devices will rotate one at a time.\n\nNote: Devices in TIMEOUT state are excluded because they failed their previous rotation attempt and require manual intervention.`,
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
        <h1 className="text-2xl font-bold text-foreground">Rotation Dashboard</h1>
        <p className="mt-4 text-destructive">Failed to load rotation data: {error.message}</p>
      </div>
    )
  }

  return (
    <div className="p-8" data-testid="rotation.dashboard">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Rotation Dashboard</h1>
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

      {/* Stacked Bar Chart */}
      {isLoading ? (
        <Skeleton className="h-8 mb-6" />
      ) : (
        <div className="mb-6" data-testid="rotation.dashboard.summary">
          <StackedBar
            healthy={counts.healthy ?? 0}
            warning={counts.warning ?? 0}
            critical={counts.critical ?? 0}
          />
        </div>
      )}

      {/* Schedule Info */}
      {status && (
        <div className="mb-6 bg-card rounded-lg p-4 border border-border" data-testid="rotation.dashboard.schedule">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="text-muted-foreground text-sm">Last Rotation Completed</div>
              <div className="text-foreground">{formatDate(status.lastRotationCompletedAt)}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-sm">Next Scheduled Rotation</div>
              <div className="text-foreground">{formatDate(status.nextScheduledRotation)}</div>
            </div>
            <div>
              <div className="text-muted-foreground text-sm">Currently Pending</div>
              {status.pendingDeviceId ? (
                <Link
                  to="/devices/$deviceId"
                  params={{ deviceId: String(status.pendingDeviceId) }}
                  className="inline-flex items-center gap-1 text-link hover:text-link-hover"
                  data-testid="rotation.dashboard.pending-device-link"
                >
                  View Device
                  <ExternalLink className="h-3 w-3" />
                </Link>
              ) : (
                <div className="text-foreground" data-testid="rotation.dashboard.no-pending">
                  None
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Category Panels */}
      {isLoading ? (
        <div className="space-y-4" data-testid="rotation.dashboard.loading">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-4" data-testid="rotation.dashboard.panels">
          <CategoryPanel
            category="healthy"
            devices={healthy}
            isExpanded={panelState.healthy}
            onToggle={() => togglePanel('healthy')}
            modelNameMap={modelNameMap}
          />
          <CategoryPanel
            category="warning"
            devices={warning}
            isExpanded={panelState.warning}
            onToggle={() => togglePanel('warning')}
            modelNameMap={modelNameMap}
          />
          <CategoryPanel
            category="critical"
            devices={critical}
            isExpanded={panelState.critical}
            onToggle={() => togglePanel('critical')}
            modelNameMap={modelNameMap}
          />
        </div>
      )}

      <ConfirmDialog {...confirmProps} contentProps={{ 'data-testid': 'rotation.dashboard.confirm-dialog' }} />
    </div>
  )
}
