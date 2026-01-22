import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetConfigs,
  useGetConfigsByConfigId,
  usePostConfigs,
  usePutConfigsByConfigId,
  useDeleteConfigsByConfigId,
  type ConfigCreateRequestSchema_6be28b6,
  type ConfigUpdateRequestSchema_6be28b6
} from '@/lib/api/generated/hooks'
import { useToast } from '@/contexts/toast-context'

// UI domain model (camelCase) - now includes id for ID-based operations
export interface DeviceConfig {
  id: number
  macAddress: string
  deviceName: string
  deviceEntityId: string
  enableOta: boolean | null
}

// Full device config with content (returned from single-config endpoints)
export interface DeviceConfigWithContent extends DeviceConfig {
  content: Record<string, unknown>
  createdAt: string
  updatedAt: string
}

// Transform snake_case API response to camelCase UI model
function transformConfigSummary(apiConfig: {
  id: number
  mac_address: string
  device_name: string | null
  device_entity_id: string | null
  enable_ota: boolean | null
}): DeviceConfig {
  return {
    id: apiConfig.id,
    macAddress: apiConfig.mac_address,
    deviceName: apiConfig.device_name || '',
    deviceEntityId: apiConfig.device_entity_id || '',
    enableOta: apiConfig.enable_ota
  }
}

// Transform full config response to camelCase UI model
function transformConfigResponse(apiConfig: {
  id: number
  mac_address: string
  device_name: string | null
  device_entity_id: string | null
  enable_ota: boolean | null
  content: Record<string, unknown>
  created_at: string
  updated_at: string
}): DeviceConfigWithContent {
  return {
    id: apiConfig.id,
    macAddress: apiConfig.mac_address,
    deviceName: apiConfig.device_name || '',
    deviceEntityId: apiConfig.device_entity_id || '',
    enableOta: apiConfig.enable_ota,
    content: apiConfig.content,
    createdAt: apiConfig.created_at,
    updatedAt: apiConfig.updated_at
  }
}

// Hook to fetch all device configs
export function useDevices() {
  const query = useGetConfigs()

  const devices = useMemo(() => {
    if (!query.data?.configs) return []
    return query.data.configs.map(transformConfigSummary)
  }, [query.data])

  return {
    ...query,
    devices
  }
}

// Hook to fetch a single device config by ID
export function useDevice(deviceId: number | undefined) {
  const query = useGetConfigsByConfigId(
    { path: { config_id: deviceId! } },
    { enabled: deviceId !== undefined }
  )

  const device = useMemo(() => {
    if (!query.data) return null
    return transformConfigResponse(query.data)
  }, [query.data])

  // Alias for backward compatibility - returns just the content
  const config = device?.content ?? null

  return {
    ...query,
    device,
    config
  }
}

// Hook to create a new device config
export function useCreateDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePostConfigs({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getConfigs'] })
      showSuccess('Device configuration created successfully')
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to create device configuration'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { macAddress: string; content: Record<string, unknown> },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      // API expects content as a JSON string
      const body: ConfigCreateRequestSchema_6be28b6 = {
        mac_address: variables.macAddress,
        content: JSON.stringify(variables.content)
      }
      mutation.mutate({ body }, options)
    },
    mutateAsync: async (variables: { macAddress: string; content: Record<string, unknown> }) => {
      const body: ConfigCreateRequestSchema_6be28b6 = {
        mac_address: variables.macAddress,
        content: JSON.stringify(variables.content)
      }
      return mutation.mutateAsync({ body })
    }
  }
}

// Hook to update an existing device config by ID
export function useUpdateDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePutConfigsByConfigId({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getConfigs'] })
      queryClient.invalidateQueries({ queryKey: ['getConfigsByConfigId'] })
      showSuccess('Device configuration updated successfully')
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to update device configuration'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { id: number; content: Record<string, unknown> },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      // API expects content as a JSON string
      const body: ConfigUpdateRequestSchema_6be28b6 = {
        content: JSON.stringify(variables.content)
      }
      mutation.mutate({ path: { config_id: variables.id }, body }, options)
    },
    mutateAsync: async (variables: { id: number; content: Record<string, unknown> }) => {
      const body: ConfigUpdateRequestSchema_6be28b6 = {
        content: JSON.stringify(variables.content)
      }
      return mutation.mutateAsync({ path: { config_id: variables.id }, body })
    }
  }
}

// Hook to delete a device config by ID
export function useDeleteDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = useDeleteConfigsByConfigId({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getConfigs'] })
      showSuccess('Device configuration deleted successfully')
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to delete device configuration'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { id: number },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      mutation.mutate({ path: { config_id: variables.id } }, options)
    },
    mutateAsync: (variables: { id: number }) => {
      return mutation.mutateAsync({ path: { config_id: variables.id } })
    }
  }
}
