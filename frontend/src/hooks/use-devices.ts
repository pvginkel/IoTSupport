import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetDevices,
  useGetDevicesByDeviceId,
  usePostDevices,
  usePutDevicesByDeviceId,
  useDeleteDevicesByDeviceId,
  useGetDevicesKeycloakStatusByDeviceId,
  usePostDevicesKeycloakSyncByDeviceId,
  type DeviceCreateSchema_d48fbce,
  type DeviceUpdateSchema_d48fbce
} from '@/lib/api/generated/hooks'
import { useToast } from '@/hooks/use-toast'

// UI domain model (camelCase) - device summary for list view
export interface DeviceSummary {
  id: number
  key: string
  deviceModelId: number
  deviceName: string
  deviceEntityId: string
  enableOta: boolean | null
  rotationState: string
  secretCreatedAt: string | null
  lastCoredumpAt: string | null
}

// Full device with content and model info (returned from single-device endpoints)
export interface Device {
  id: number
  key: string
  deviceModelId: number
  deviceModel: {
    id: number
    code: string
    name: string
    firmwareVersion: string | null
  }
  config: string
  deviceName: string
  deviceEntityId: string
  enableOta: boolean | null
  rotationState: string
  clientId: string
  secretCreatedAt: string | null
  lastRotationAttemptAt: string | null
  lastRotationCompletedAt: string | null
  createdAt: string
  updatedAt: string
}

// Transform snake_case API response to camelCase UI model (list view)
function transformDeviceSummary(apiDevice: {
  id: number
  key: string
  device_model_id: number
  device_name: string | null
  device_entity_id: string | null
  enable_ota: boolean | null
  rotation_state: string
  secret_created_at?: string | null
  last_coredump_at?: string | null
}): DeviceSummary {
  return {
    id: apiDevice.id,
    key: apiDevice.key,
    deviceModelId: apiDevice.device_model_id,
    deviceName: apiDevice.device_name || '',
    deviceEntityId: apiDevice.device_entity_id || '',
    enableOta: apiDevice.enable_ota,
    rotationState: apiDevice.rotation_state,
    secretCreatedAt: apiDevice.secret_created_at ?? null,
    lastCoredumpAt: apiDevice.last_coredump_at ?? null
  }
}

// Transform full device response to camelCase UI model
function transformDeviceResponse(apiDevice: {
  id: number
  key: string
  device_model_id: number
  device_model: {
    id: number
    code: string
    name: string
    firmware_version?: string | null
  }
  config: string
  device_name: string | null
  device_entity_id: string | null
  enable_ota: boolean | null
  rotation_state: string
  client_id: string
  secret_created_at?: string | null
  last_rotation_attempt_at?: string | null
  last_rotation_completed_at?: string | null
  created_at: string
  updated_at: string
}): Device {
  return {
    id: apiDevice.id,
    key: apiDevice.key,
    deviceModelId: apiDevice.device_model_id,
    deviceModel: {
      id: apiDevice.device_model.id,
      code: apiDevice.device_model.code,
      name: apiDevice.device_model.name,
      firmwareVersion: apiDevice.device_model.firmware_version ?? null
    },
    config: apiDevice.config,
    deviceName: apiDevice.device_name || '',
    deviceEntityId: apiDevice.device_entity_id || '',
    enableOta: apiDevice.enable_ota,
    rotationState: apiDevice.rotation_state,
    clientId: apiDevice.client_id,
    secretCreatedAt: apiDevice.secret_created_at ?? null,
    lastRotationAttemptAt: apiDevice.last_rotation_attempt_at ?? null,
    lastRotationCompletedAt: apiDevice.last_rotation_completed_at ?? null,
    createdAt: apiDevice.created_at,
    updatedAt: apiDevice.updated_at
  }
}

// Hook to fetch all devices
export function useDevices() {
  const query = useGetDevices()

  const devices = useMemo(() => {
    if (!query.data?.devices) return []
    return query.data.devices.map(transformDeviceSummary)
  }, [query.data])

  return {
    ...query,
    devices
  }
}

// Hook to fetch a single device by ID
export function useDevice(deviceId: number | undefined) {
  const query = useGetDevicesByDeviceId(
    { path: { device_id: deviceId! } },
    { enabled: deviceId !== undefined }
  )

  const device = useMemo(() => {
    if (!query.data) return null
    return transformDeviceResponse(query.data)
  }, [query.data])

  return {
    ...query,
    device
  }
}

// Hook to create a new device
export function useCreateDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePostDevices({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getDevices'] })
      showSuccess('Device created successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to create device'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { deviceModelId: number; config: string },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      const body: DeviceCreateSchema_d48fbce = {
        device_model_id: variables.deviceModelId,
        config: variables.config
      }
      mutation.mutate({ body }, options)
    },
    mutateAsync: async (variables: { deviceModelId: number; config: string }) => {
      const body: DeviceCreateSchema_d48fbce = {
        device_model_id: variables.deviceModelId,
        config: variables.config
      }
      return mutation.mutateAsync({ body })
    }
  }
}

// Hook to update an existing device by ID
export function useUpdateDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePutDevicesByDeviceId({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getDevices'] })
      queryClient.invalidateQueries({ queryKey: ['getDevicesByDeviceId'] })
      showSuccess('Device updated successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to update device'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { id: number; config: string },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      const body: DeviceUpdateSchema_d48fbce = {
        config: variables.config
      }
      mutation.mutate({ path: { device_id: variables.id }, body }, options)
    },
    mutateAsync: async (variables: { id: number; config: string }) => {
      const body: DeviceUpdateSchema_d48fbce = {
        config: variables.config
      }
      return mutation.mutateAsync({ path: { device_id: variables.id }, body })
    }
  }
}

// Hook to delete a device by ID
export function useDeleteDevice() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = useDeleteDevicesByDeviceId({
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['getDevices'] })
      showSuccess('Device deleted successfully')
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : 'Failed to delete device'
      showError(message)
    }
  })

  return {
    ...mutation,
    mutate: (
      variables: { id: number },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      mutation.mutate({ path: { device_id: variables.id } }, options)
    },
    mutateAsync: (variables: { id: number }) => {
      return mutation.mutateAsync({ path: { device_id: variables.id } })
    }
  }
}

// UI domain model for Keycloak client status
export interface KeycloakClientStatus {
  clientId: string
  exists: boolean
  consoleUrl: string | null
  keycloakUuid: string | null
}

// Transform snake_case API response to camelCase UI model
function transformKeycloakStatus(apiStatus: {
  client_id: string
  exists: boolean
  console_url: string | null
  keycloak_uuid: string | null
}): KeycloakClientStatus {
  return {
    clientId: apiStatus.client_id,
    exists: apiStatus.exists,
    consoleUrl: apiStatus.console_url,
    keycloakUuid: apiStatus.keycloak_uuid
  }
}

// Hook to fetch Keycloak client status for a device
export function useDeviceKeycloakStatus(deviceId: number | undefined) {
  const query = useGetDevicesKeycloakStatusByDeviceId(
    { path: { device_id: deviceId! } },
    { enabled: deviceId !== undefined }
  )

  const status = useMemo(() => {
    if (!query.data) return null
    return transformKeycloakStatus(query.data)
  }, [query.data])

  return {
    ...query,
    status
  }
}

// Hook to sync (recreate) Keycloak client for a device
export function useSyncDeviceKeycloak() {
  const { showSuccess, showError } = useToast()
  const queryClient = useQueryClient()
  const mutation = usePostDevicesKeycloakSyncByDeviceId()

  return {
    ...mutation,
    mutate: (
      variables: { deviceId: number },
      options?: { onSuccess?: () => void; onError?: (error: Error) => void }
    ) => {
      mutation.mutate(
        { path: { device_id: variables.deviceId } },
        {
          onSuccess: () => {
            queryClient.invalidateQueries({
              queryKey: ['getDevicesKeycloakStatusByDeviceId', { path: { device_id: variables.deviceId } }]
            })
            showSuccess('Keycloak client created successfully')
            options?.onSuccess?.()
          },
          onError: (error: unknown) => {
            const message = error instanceof Error ? error.message : 'Failed to create Keycloak client'
            showError(message)
            if (error instanceof Error) {
              options?.onError?.(error)
            }
          }
        }
      )
    },
    mutateAsync: async (variables: { deviceId: number }) => {
      const result = await mutation.mutateAsync({ path: { device_id: variables.deviceId } })
      queryClient.invalidateQueries({
        queryKey: ['getDevicesKeycloakStatusByDeviceId', { path: { device_id: variables.deviceId } }]
      })
      showSuccess('Keycloak client created successfully')
      return result
    }
  }
}
