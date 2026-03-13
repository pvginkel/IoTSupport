import { Link } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import type { Device } from '@/hooks/use-devices'
import { useCoredumps } from '@/hooks/use-coredumps'
import { getRotationStateBadge } from '@/lib/utils/device-badges'
import { RoutedTabs, type RoutedTabDefinition } from '@/components/primitives'

/** localStorage key for persisting the active device detail tab. */
export const DEVICE_TAB_STORAGE_KEY = 'iot-support-device-tab'

/** Valid device tab values for preference persistence. */
export const DEVICE_TAB_VALUES = ['edit', 'logs', 'coredumps'] as const

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

  const deviceIdStr = String(device.id)
  const basePath = `/devices/${deviceIdStr}/`

  // Build tab definitions with the coredumps badge composed as a ReactNode label
  const tabs: RoutedTabDefinition[] = [
    {
      to: '/devices/$deviceId/edit',
      params: { deviceId: deviceIdStr },
      value: 'edit',
      label: 'Configuration',
      testId: 'devices.detail.tab.configuration',
    },
    {
      to: '/devices/$deviceId/logs',
      params: { deviceId: deviceIdStr },
      value: 'logs',
      label: 'Logs',
      testId: 'devices.detail.tab.logs',
    },
    {
      to: '/devices/$deviceId/coredumps',
      params: { deviceId: deviceIdStr },
      value: 'coredumps',
      label: (
        <>
          Core Dumps
          {coredumps.length > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {coredumps.length}
            </span>
          )}
        </>
      ),
      testId: 'devices.detail.tab.coredumps',
    },
  ]

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

      {/* Tab bar — delegates rendering and persistence to the RoutedTabs primitive */}
      <RoutedTabs
        tabs={tabs}
        testIdPrefix="devices.detail"
        storageKey={DEVICE_TAB_STORAGE_KEY}
        basePath={basePath}
      />
    </div>
  )
}
