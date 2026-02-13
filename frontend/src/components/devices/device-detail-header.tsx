import { Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import type { Device } from '@/hooks/use-devices'
import { useCoredumps } from '@/hooks/use-coredumps'
import { getRotationStateBadge } from '@/lib/utils/device-badges'

interface DeviceDetailHeaderProps {
  device: Device
}

/**
 * Sticky header for the device detail view.
 * Shows device identity, status badges, and tab navigation.
 */
export function DeviceDetailHeader({ device }: DeviceDetailHeaderProps) {
  const { coredumps } = useCoredumps(device.id)
  const rotationBadge = getRotationStateBadge(device.rotationState)

  // Title: prefer name, then entity ID, then key
  const displayTitle = (device.deviceName && device.deviceName.trim())
    ? device.deviceName
    : null
  const displaySubtitle = (device.deviceEntityId && device.deviceEntityId.trim())
    ? device.deviceEntityId
    : null

  return (
    <div
      className="sticky top-0 z-10 border-b border-border bg-background"
      data-testid="devices.detail.header"
    >
      <div className="p-4 pb-0">
        {/* Back link + title */}
        <div className="flex items-center gap-3 mb-3">
          <Link
            to="/devices"
            className="text-muted-foreground hover:text-foreground"
            data-testid="devices.detail.header.back"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <h1 className="text-2xl font-bold text-foreground">
            {displayTitle
              ? `Edit Device: ${displayTitle}`
              : displaySubtitle
                ? <>Edit Device: <span className="font-mono">{displaySubtitle}</span></>
                : <>Edit Device: <span className="font-mono">{device.key}</span></>
            }
          </h1>
        </div>

        {/* Identity row: device key, model, status badges */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mb-3 text-sm">
          {/* Device key */}
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Key:</span>
            <span className="font-mono text-foreground" data-testid="devices.detail.header.device-key">
              {device.key}
            </span>
          </div>

          {/* Model name + code as link */}
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Model:</span>
            <Link
              to="/device-models/$modelId"
              params={{ modelId: String(device.deviceModelId) }}
              className="text-link hover:text-link-hover hover:underline"
              data-testid="devices.detail.header.device-model"
            >
              {device.deviceModel.name} ({device.deviceModel.code})
            </Link>
          </div>

          {/* Rotation state badge */}
          <span
            className={`px-2 py-0.5 rounded-md text-xs ${rotationBadge.bgColor} ${rotationBadge.textColor}`}
            data-testid="devices.detail.header.rotation-badge"
          >
            {device.rotationState}
          </span>

          {/* OTA status */}
          <div className="flex items-center gap-1" data-testid="devices.detail.header.ota-badge">
            <span className="text-muted-foreground">OTA:</span>
            {device.enableOta === true && <span className="text-green-400">Enabled</span>}
            {device.enableOta === false && <span className="text-red-400">Disabled</span>}
            {device.enableOta === null && <span className="text-muted-foreground/50">N/A</span>}
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <nav className="flex gap-0 px-4" data-testid="devices.detail.tabs">
        <TabLink
          to="/devices/$deviceId"
          params={{ deviceId: String(device.id) }}
          exact
          testId="devices.detail.tab.configuration"
        >
          Configuration
        </TabLink>
        <TabLink
          to="/devices/$deviceId/logs"
          params={{ deviceId: String(device.id) }}
          testId="devices.detail.tab.logs"
        >
          Logs
        </TabLink>
        <TabLink
          to="/devices/$deviceId/coredumps"
          params={{ deviceId: String(device.id) }}
          testId="devices.detail.tab.coredumps"
        >
          Core Dumps
          {coredumps.length > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {coredumps.length}
            </span>
          )}
        </TabLink>
      </nav>
    </div>
  )
}

/** Tab link styled to match the sidebar active-link pattern */
function TabLink({
  to,
  params,
  exact,
  testId,
  children,
}: {
  to: string
  params: Record<string, string>
  exact?: boolean
  testId: string
  children: React.ReactNode
}) {
  return (
    <Link
      to={to}
      params={params}
      activeOptions={exact ? { exact: true } : undefined}
      className="relative px-4 py-2.5 text-sm font-medium transition-colors text-muted-foreground hover:text-foreground [&.active]:text-foreground"
      activeProps={{
        className: 'active',
        'aria-current': 'page',
      }}
      data-testid={testId}
    >
      {children}
      {/* Active underline indicator rendered via CSS */}
      <span className="absolute inset-x-0 bottom-0 h-0.5 bg-transparent [.active>&]:bg-primary" />
    </Link>
  )
}
