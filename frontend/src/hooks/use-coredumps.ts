import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetDevicesCoredumpsByDeviceId,
  useGetDevicesCoredumpsByDeviceIdAndCoredumpId,
  useDeleteDevicesCoredumpsByDeviceIdAndCoredumpId
} from '@/lib/api/generated/hooks'
import { useToast } from '@/contexts/toast-context'

// UI domain model (camelCase) - coredump summary for list view
export interface CoredumpSummary {
  id: number
  deviceId: number
  chip: string
  firmwareVersion: string
  size: number
  parseStatus: string
  parsedAt: string | null
  uploadedAt: string
  createdAt: string
}

// Full coredump with parsed output (returned from detail endpoint)
export interface CoredumpDetail extends CoredumpSummary {
  parsedOutput: string | null
  updatedAt: string
}

// Transform snake_case API response to camelCase UI model (list view)
function transformCoredumpSummary(apiCoredump: {
  id: number
  device_id: number
  chip: string
  firmware_version: string
  size: number
  parse_status: string
  parsed_at: string | null
  uploaded_at: string
  created_at: string
}): CoredumpSummary {
  return {
    id: apiCoredump.id,
    deviceId: apiCoredump.device_id,
    chip: apiCoredump.chip,
    firmwareVersion: apiCoredump.firmware_version,
    size: apiCoredump.size,
    parseStatus: apiCoredump.parse_status,
    parsedAt: apiCoredump.parsed_at,
    uploadedAt: apiCoredump.uploaded_at,
    createdAt: apiCoredump.created_at
  }
}

// Transform snake_case API response to camelCase UI model (detail view)
function transformCoredumpDetail(apiCoredump: {
  id: number
  device_id: number
  chip: string
  firmware_version: string
  size: number
  parse_status: string
  parsed_at: string | null
  parsed_output: string | null
  uploaded_at: string
  created_at: string
  updated_at: string
}): CoredumpDetail {
  return {
    ...transformCoredumpSummary(apiCoredump),
    parsedOutput: apiCoredump.parsed_output,
    updatedAt: apiCoredump.updated_at
  }
}

// Hook to fetch all coredumps for a device
export function useCoredumps(deviceId: number | undefined) {
  const query = useGetDevicesCoredumpsByDeviceId(
    { path: { device_id: deviceId! } },
    { enabled: deviceId !== undefined }
  )

  const coredumps = useMemo(() => {
    if (!query.data?.coredumps) return []
    return query.data.coredumps.map(transformCoredumpSummary)
  }, [query.data])

  return {
    ...query,
    coredumps
  }
}

// Hook to fetch a single coredump detail
export function useCoredump(deviceId: number | undefined, coredumpId: number | undefined) {
  const query = useGetDevicesCoredumpsByDeviceIdAndCoredumpId(
    { path: { device_id: deviceId!, coredump_id: coredumpId! } },
    { enabled: deviceId !== undefined && coredumpId !== undefined }
  )

  const coredump = useMemo(() => {
    if (!query.data) return null
    return transformCoredumpDetail(query.data)
  }, [query.data])

  return {
    ...query,
    coredump
  }
}

// Hook to delete a single coredump
export function useDeleteCoredump() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = useDeleteDevicesCoredumpsByDeviceIdAndCoredumpId({
    onSuccess: () => {
      // Invalidate coredump list and device list (to refresh lastCoredumpAt)
      queryClient.invalidateQueries({ queryKey: ['getDevicesCoredumpsByDeviceId'] })
      queryClient.invalidateQueries({ queryKey: ['getDevices'] })
      showSuccess('Core dump deleted successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to delete core dump'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { deviceId: number; coredumpId: number },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      mutation.mutate(
        { path: { device_id: variables.deviceId, coredump_id: variables.coredumpId } },
        {
          onSuccess: () => options?.onSuccess?.(),
          onError: (err) => {
            if (err instanceof Error) options?.onError?.(err)
          }
        }
      )
    },
    mutateAsync: (variables: { deviceId: number; coredumpId: number }) => {
      return mutation.mutateAsync(
        { path: { device_id: variables.deviceId, coredump_id: variables.coredumpId } }
      )
    }
  }
}

// Re-export formatFileSize from utils for convenience
export { formatFileSize } from '@/lib/utils/format'
