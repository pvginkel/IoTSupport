import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetConfigs,
  useGetConfigsByMacAddress,
  usePutConfigsByMacAddress,
  useDeleteConfigsByMacAddress,
  type ConfigSaveRequestSchema_6be28b6
} from '@/lib/api/generated/hooks'
import { useToast } from '@/contexts/toast-context'

// UI domain model (camelCase)
export interface DeviceConfig {
  macAddress: string
  deviceName: string
  deviceEntityId: string
  enableOta: boolean | null
}

// Transform snake_case API response to camelCase UI model
function transformConfigSummary(apiConfig: {
  mac_address: string
  device_name: string | null
  device_entity_id: string | null
  enable_ota: boolean | null
}): DeviceConfig {
  return {
    macAddress: apiConfig.mac_address,
    deviceName: apiConfig.device_name || '',
    deviceEntityId: apiConfig.device_entity_id || '',
    enableOta: apiConfig.enable_ota
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

// Hook to fetch a single device config
export function useDevice(macAddress: string) {
  const query = useGetConfigsByMacAddress(
    { path: { mac_address: macAddress } },
    { enabled: !!macAddress }
  )

  const config = useMemo(() => {
    if (!query.data?.content) return null
    return query.data.content
  }, [query.data])

  return {
    ...query,
    config
  }
}

// Hook to save a device config
export function useSaveDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePutConfigsByMacAddress({
    onSuccess: () => {
      // Manually invalidate to ensure list updates (generated hook's invalidation may be overridden)
      queryClient.invalidateQueries({ queryKey: ['getConfigs'] })
      showSuccess('Device configuration saved successfully')
    },
    onError: (error) => {
      const message = error instanceof Error ? error.message : 'Failed to save device configuration'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { macAddress: string; config: ConfigSaveRequestSchema_6be28b6 },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      mutation.mutate(
        { path: { mac_address: variables.macAddress }, body: variables.config },
        options
      )
    },
    mutateAsync: (variables: { macAddress: string; config: ConfigSaveRequestSchema_6be28b6 }) => {
      return mutation.mutateAsync({ path: { mac_address: variables.macAddress }, body: variables.config })
    }
  }
}

// Hook to delete a device config
export function useDeleteDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = useDeleteConfigsByMacAddress({
    onSuccess: () => {
      // Manually invalidate to ensure list updates (generated hook's invalidation may be overridden)
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
    mutate: (variables: { macAddress: string }) => {
      mutation.mutate({ path: { mac_address: variables.macAddress } })
    },
    mutateAsync: (variables: { macAddress: string }) => {
      return mutation.mutateAsync({ path: { mac_address: variables.macAddress } })
    }
  }
}
