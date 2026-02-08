import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetDeviceModels,
  useGetDeviceModelsByModelId,
  usePostDeviceModels,
  usePutDeviceModelsByModelId,
  useDeleteDeviceModelsByModelId,
  type DeviceModelCreateSchema_349be3d,
  type DeviceModelUpdateSchema_349be3d
} from '@/lib/api/generated/hooks'
import { useToast } from '@/contexts/toast-context'

// UI domain model (camelCase) - device model summary for list view
export interface DeviceModelSummary {
  id: number
  code: string
  name: string
  hasConfigSchema: boolean
  deviceCount: number
  firmwareVersion: string | null
}

// Full device model with config schema
export interface DeviceModel {
  id: number
  code: string
  name: string
  hasConfigSchema: boolean
  configSchema: string | null
  deviceCount: number
  firmwareVersion: string | null
  createdAt: string
  updatedAt: string
}

// Transform snake_case API response to camelCase UI model (list view)
function transformDeviceModelSummary(apiModel: {
  id: number
  code: string
  name: string
  has_config_schema: boolean
  device_count: number
  firmware_version: string | null
}): DeviceModelSummary {
  return {
    id: apiModel.id,
    code: apiModel.code,
    name: apiModel.name,
    hasConfigSchema: apiModel.has_config_schema,
    deviceCount: apiModel.device_count,
    firmwareVersion: apiModel.firmware_version
  }
}

// Transform full device model response to camelCase UI model
function transformDeviceModelResponse(apiModel: {
  id: number
  code: string
  name: string
  has_config_schema: boolean
  config_schema?: string | null
  device_count: number
  firmware_version: string | null
  created_at: string
  updated_at: string
}): DeviceModel {
  return {
    id: apiModel.id,
    code: apiModel.code,
    name: apiModel.name,
    hasConfigSchema: apiModel.has_config_schema,
    configSchema: apiModel.config_schema ?? null,
    deviceCount: apiModel.device_count,
    firmwareVersion: apiModel.firmware_version,
    createdAt: apiModel.created_at,
    updatedAt: apiModel.updated_at
  }
}

// Hook to fetch all device models
export function useDeviceModels() {
  const query = useGetDeviceModels()

  const deviceModels = useMemo(() => {
    if (!query.data?.device_models) return []
    return query.data.device_models.map(transformDeviceModelSummary)
  }, [query.data])

  return {
    ...query,
    deviceModels
  }
}

// Hook to fetch a single device model by ID
export function useDeviceModel(modelId: number | undefined) {
  const query = useGetDeviceModelsByModelId(
    { path: { model_id: modelId! } },
    { enabled: modelId !== undefined }
  )

  const deviceModel = useMemo(() => {
    if (!query.data) return null
    return transformDeviceModelResponse(query.data)
  }, [query.data])

  return {
    ...query,
    deviceModel
  }
}

// Hook to create a new device model
export function useCreateDeviceModel() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePostDeviceModels({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getDeviceModels'] })
      showSuccess('Device model created successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to create device model'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { code: string; name: string; configSchema?: string | null },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      const body: DeviceModelCreateSchema_349be3d = {
        code: variables.code,
        name: variables.name,
        config_schema: variables.configSchema || null
      }
      mutation.mutate({ body }, options)
    },
    mutateAsync: async (variables: { code: string; name: string; configSchema?: string | null }) => {
      const body: DeviceModelCreateSchema_349be3d = {
        code: variables.code,
        name: variables.name,
        config_schema: variables.configSchema || null
      }
      return mutation.mutateAsync({ body })
    }
  }
}

// Hook to update an existing device model by ID
export function useUpdateDeviceModel() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePutDeviceModelsByModelId({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getDeviceModels'] })
      queryClient.invalidateQueries({ queryKey: ['getDeviceModelsByModelId'] })
      showSuccess('Device model updated successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to update device model'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { id: number; name?: string | null; configSchema?: string | null },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      // API schema requires both fields (can be null for no change)
      const body: DeviceModelUpdateSchema_349be3d = {
        name: variables.name ?? null,
        config_schema: variables.configSchema !== undefined
          ? (variables.configSchema || null)
          : null
      }
      mutation.mutate({ path: { model_id: variables.id }, body }, options)
    },
    mutateAsync: async (variables: { id: number; name?: string | null; configSchema?: string | null }) => {
      const body: DeviceModelUpdateSchema_349be3d = {
        name: variables.name ?? null,
        config_schema: variables.configSchema !== undefined
          ? (variables.configSchema || null)
          : null
      }
      return mutation.mutateAsync({ path: { model_id: variables.id }, body })
    }
  }
}

// Hook to delete a device model by ID
export function useDeleteDeviceModel() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = useDeleteDeviceModelsByModelId({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getDeviceModels'] })
      showSuccess('Device model deleted successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to delete device model'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { id: number },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      mutation.mutate({ path: { model_id: variables.id } }, options)
    },
    mutateAsync: (variables: { id: number }) => {
      return mutation.mutateAsync({ path: { model_id: variables.id } })
    }
  }
}
