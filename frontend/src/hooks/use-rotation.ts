import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetRotationDashboard,
  useGetRotationStatus,
  usePostRotationTrigger,
  type DashboardResponseSchema_57872a8
} from '@/lib/api/generated/hooks'
import { useToast } from '@/contexts/toast-context'

// Dashboard device summary (camelCase)
export interface RotationDashboardDevice {
  id: number
  key: string
  deviceName: string | null
  deviceModelCode: string
  rotationState: string
  daysSinceRotation: number | null
  lastRotationCompletedAt: string | null
  category: 'healthy' | 'warning' | 'critical'
}

// Rotation status (camelCase)
export interface RotationStatus {
  countsByState: Record<string, number>
  lastRotationCompletedAt: string | null
  nextScheduledRotation: string | null
  pendingDeviceId: number | null
}

// Transform dashboard device to camelCase
function transformDashboardDevice(
  apiDevice: {
    id: number
    key: string
    device_name: string | null
    device_model_code: string
    rotation_state: string
    days_since_rotation: number | null
    last_rotation_completed_at: string | null
  },
  category: 'healthy' | 'warning' | 'critical'
): RotationDashboardDevice {
  return {
    id: apiDevice.id,
    key: apiDevice.key,
    deviceName: apiDevice.device_name,
    deviceModelCode: apiDevice.device_model_code,
    rotationState: apiDevice.rotation_state,
    daysSinceRotation: apiDevice.days_since_rotation,
    lastRotationCompletedAt: apiDevice.last_rotation_completed_at,
    category
  }
}

// Transform status response to camelCase
function transformStatus(apiStatus: {
  counts_by_state: Record<string, number>
  last_rotation_completed_at: string | null
  next_scheduled_rotation: string | null
  pending_device_id: number | null
}): RotationStatus {
  return {
    countsByState: apiStatus.counts_by_state,
    lastRotationCompletedAt: apiStatus.last_rotation_completed_at,
    nextScheduledRotation: apiStatus.next_scheduled_rotation,
    pendingDeviceId: apiStatus.pending_device_id
  }
}

// Polling interval for active rotation (30 seconds)
const ROTATION_ACTIVE_POLLING_INTERVAL = 30_000

// Hook to fetch rotation dashboard data
export function useRotationDashboard() {
  // Use refetchInterval as a function to dynamically enable polling when rotation is active
  const query = useGetRotationDashboard(undefined, {
    refetchInterval: (query) => {
      const data = query.state.data as DashboardResponseSchema_57872a8 | undefined
      const counts = data?.counts ?? {}
      const pendingCount = counts['PENDING'] ?? 0
      const queuedCount = counts['QUEUED'] ?? 0
      const isActive = pendingCount > 0 || queuedCount > 0
      return isActive ? ROTATION_ACTIVE_POLLING_INTERVAL : false
    }
  })

  // Transform devices by category
  const healthy = useMemo(() => {
    if (!query.data?.healthy) return []
    return query.data.healthy.map(d => transformDashboardDevice(d, 'healthy'))
  }, [query.data])

  const warning = useMemo(() => {
    if (!query.data?.warning) return []
    return query.data.warning.map(d => transformDashboardDevice(d, 'warning'))
  }, [query.data])

  const critical = useMemo(() => {
    if (!query.data?.critical) return []
    return query.data.critical.map(d => transformDashboardDevice(d, 'critical'))
  }, [query.data])

  // Combined list for backward compatibility
  const devices = useMemo(() => {
    return [...healthy, ...warning, ...critical]
  }, [healthy, warning, critical])

  // Get counts from the dashboard response
  const counts = useMemo(() => {
    return query.data?.counts ?? {}
  }, [query.data])

  // Compute isRotationActive for consumers
  const isRotationActive = useMemo(() => {
    const pendingCount = counts['PENDING'] ?? 0
    const queuedCount = counts['QUEUED'] ?? 0
    return pendingCount > 0 || queuedCount > 0
  }, [counts])

  return {
    ...query,
    devices,
    healthy,
    warning,
    critical,
    counts,
    isRotationActive
  }
}

// Hook to fetch rotation status
export function useRotationStatus() {
  const query = useGetRotationStatus()

  const status = useMemo(() => {
    if (!query.data) return null
    return transformStatus(query.data)
  }, [query.data])

  return {
    ...query,
    status
  }
}

// Hook to trigger fleet-wide rotation
export function useTriggerRotation() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePostRotationTrigger({
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['getRotationDashboard'] })
      queryClient.invalidateQueries({ queryKey: ['getRotationStatus'] })
      queryClient.invalidateQueries({ queryKey: ['getDevices'] })
      // Type assertion for the response
      const response = data as { devices_queued?: number }
      const count = response.devices_queued ?? 0
      showSuccess(`Rotation triggered for ${count} device${count !== 1 ? 's' : ''}`)
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to trigger rotation'
      showError(message)
    }
  })

  return mutation
}
