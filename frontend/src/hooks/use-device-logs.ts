import { useState, useEffect, useRef, useCallback, useReducer } from 'react'
import { isTestMode } from '@/lib/config/test-mode'
import { emitTestEvent } from '@/lib/test/event-emitter'
import { TestEventKind, type ListLoadingTestEvent } from '@/types/test-events'

// UI domain model (camelCase) - log entry
export interface LogEntry {
  message: string
  timestamp: string
}

// API response shape (snake_case)
interface DeviceLogsApiResponse {
  logs: Array<{ message: string; timestamp: string }>
  has_more: boolean
  window_start: string | null
  window_end: string | null
}

// Hook state interface
export interface UseDeviceLogsState {
  logs: LogEntry[]
  isLoading: boolean
  hasEntityId: boolean
  isPolling: boolean
}

// Hook actions interface
export interface UseDeviceLogsActions {
  startPolling: () => void
  stopPolling: () => void
}

// Hook return type
export type UseDeviceLogsResult = UseDeviceLogsState & UseDeviceLogsActions

// Constants
const POLL_INTERVAL_MS = 1000
const MAX_BUFFER_SIZE = 1000

// Reducer for logs state management
type LogsAction =
  | { type: 'RESET' }
  | { type: 'APPEND'; logs: LogEntry[] }

function logsReducer(state: LogEntry[], action: LogsAction): LogEntry[] {
  switch (action.type) {
    case 'RESET':
      return []
    case 'APPEND': {
      const combined = [...state, ...action.logs]
      // FIFO eviction if over limit
      if (combined.length > MAX_BUFFER_SIZE) {
        return combined.slice(combined.length - MAX_BUFFER_SIZE)
      }
      return combined
    }
    default:
      return state
  }
}

interface UseDeviceLogsOptions {
  /** Device ID for fetching logs */
  deviceId: number | undefined
  /** Device entity ID - logs are only fetched if this is set */
  deviceEntityId: string | undefined
  /** Whether polling is enabled by default (default: true) */
  defaultPolling?: boolean
}

/**
 * Custom hook for cursor-based polling of device logs from Elasticsearch.
 *
 * Key behaviors:
 * - Only fetches logs if deviceEntityId is provided
 * - Polls every 1 second when polling is enabled
 * - Uses cursor-based pagination (windowEnd from previous fetch becomes start for next)
 * - Immediately fetches again if hasMore is true (catching up)
 * - Pauses polling when tab is backgrounded
 * - Silent error handling (no toasts)
 * - Max buffer of 1000 entries with FIFO eviction
 */
export function useDeviceLogs({
  deviceId,
  deviceEntityId,
  defaultPolling = true
}: UseDeviceLogsOptions): UseDeviceLogsResult {
  // State - use reducer for logs to allow dispatch without triggering the set-state-in-effect rule
  const [logs, dispatchLogs] = useReducer(logsReducer, [])
  const [isLoading, setIsLoading] = useState(false)
  const [isPolling, setIsPolling] = useState(defaultPolling)

  // Derived state
  const hasEntityId = Boolean(deviceEntityId && deviceEntityId.trim() !== '')

  // Start polling
  const startPolling = useCallback(() => {
    setIsPolling(true)
  }, [])

  // Stop polling (will be enhanced in the effect)
  const stopPollingRef = useRef<() => void>(() => {
    setIsPolling(false)
  })

  const stopPolling = useCallback(() => {
    stopPollingRef.current()
  }, [])

  // Reset logs when device changes - separate effect with dispatch
  useEffect(() => {
    dispatchLogs({ type: 'RESET' })
  }, [deviceId])

  // Main polling effect
  useEffect(() => {
    // Refs for managing async operations within this effect
    let abortController: AbortController | null = null
    let pollingTimeout: ReturnType<typeof setTimeout> | null = null
    let cursor: string | null = null
    let isInitialFetch = true
    let hasEmittedReady = false
    let isMounted = true

    // Update stop polling to include cleanup
    stopPollingRef.current = () => {
      setIsPolling(false)
      if (pollingTimeout) {
        clearTimeout(pollingTimeout)
        pollingTimeout = null
      }
      abortController?.abort()
    }

    // Emit instrumentation events in test mode
    const emitLoadingEvent = (phase: 'loading' | 'ready', logCount: number) => {
      if (!isTestMode() || deviceId === undefined) return

      const payload: Omit<ListLoadingTestEvent, 'timestamp'> = {
        kind: TestEventKind.LIST_LOADING,
        scope: 'devices.logs',
        phase,
        metadata: {
          deviceId,
          logCount,
          isPolling
        }
      }
      emitTestEvent(payload)
    }

    // Fetch logs from the API
    const fetchLogs = async (start?: string): Promise<{
      newLogs: LogEntry[]
      hasMore: boolean
      windowEnd: string | null
    } | null> => {
      if (deviceId === undefined || !hasEntityId || !isMounted) {
        return null
      }

      // Create new abort controller for this fetch
      abortController?.abort()
      abortController = new AbortController()

      try {
        // Build URL with query parameters
        const url = new URL(`/api/devices/${deviceId}/logs`, window.location.origin)
        if (start) {
          url.searchParams.set('start', start)
        }

        const response = await fetch(url.toString(), {
          signal: abortController.signal,
          credentials: 'include'
        })

        if (!response.ok) {
          // Silent error handling - just log to console for debugging
          console.debug(`[useDeviceLogs] Fetch failed: ${response.status} ${response.statusText}`)
          return null
        }

        const data: DeviceLogsApiResponse = await response.json()

        // Transform snake_case to camelCase
        const newLogs: LogEntry[] = data.logs.map(log => ({
          message: log.message,
          timestamp: log.timestamp
        }))

        return {
          newLogs,
          hasMore: data.has_more,
          windowEnd: data.window_end
        }
      } catch (error) {
        // Ignore abort errors
        if (error instanceof Error && error.name === 'AbortError') {
          return null
        }
        // Silent error handling for other errors
        console.debug('[useDeviceLogs] Fetch error:', error)
        return null
      }
    }

    // Main polling function
    const poll = async () => {
      if (!isMounted) return

      // Clear any existing timeout
      if (pollingTimeout) {
        clearTimeout(pollingTimeout)
        pollingTimeout = null
      }

      // Emit loading event for initial fetch
      if (isInitialFetch) {
        setIsLoading(true)
        emitLoadingEvent('loading', 0)
      }

      // Fetch with cursor (or without for initial fetch)
      const result = await fetchLogs(cursor ?? undefined)

      if (!isMounted) return

      if (result) {
        const { newLogs, hasMore, windowEnd } = result

        // Update cursor for next fetch
        if (windowEnd) {
          cursor = windowEnd
        }

        // Append new logs
        if (newLogs.length > 0) {
          dispatchLogs({ type: 'APPEND', logs: newLogs })
        }

        // If hasMore, immediately fetch again (catching up)
        if (hasMore && isMounted) {
          pollingTimeout = setTimeout(poll, 0)
          return
        }

        // Emit ready event after initial fetch completes (only once)
        if (isInitialFetch) {
          setIsLoading(false)
          isInitialFetch = false
          if (!hasEmittedReady) {
            hasEmittedReady = true
            emitLoadingEvent('ready', newLogs.length)
          }
        }
      } else if (isInitialFetch) {
        // Initial fetch failed or was aborted
        setIsLoading(false)
        isInitialFetch = false
        if (!hasEmittedReady) {
          hasEmittedReady = true
          emitLoadingEvent('ready', 0)
        }
      }

      // Schedule next poll if still polling and mounted
      if (isPolling && hasEntityId && isMounted) {
        pollingTimeout = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    // Visibility change handler
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        // Pause polling when tab is hidden
        if (pollingTimeout) {
          clearTimeout(pollingTimeout)
          pollingTimeout = null
        }
      } else if (document.visibilityState === 'visible' && isPolling && hasEntityId && isMounted) {
        // Resume polling when tab becomes visible
        poll()
      }
    }

    // Only start polling if we have entity ID and polling is enabled
    if (!hasEntityId || !isPolling || deviceId === undefined) {
      return
    }

    // Add visibility change listener
    document.addEventListener('visibilitychange', handleVisibilityChange)

    // Start polling
    poll()

    // Cleanup on unmount or dependency change
    return () => {
      isMounted = false
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      if (pollingTimeout) {
        clearTimeout(pollingTimeout)
      }
      abortController?.abort()
    }
  }, [deviceId, hasEntityId, isPolling])

  return {
    logs,
    isLoading,
    hasEntityId,
    isPolling,
    startPolling,
    stopPolling
  }
}
