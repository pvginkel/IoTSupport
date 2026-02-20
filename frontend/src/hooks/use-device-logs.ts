import { useEffect, useCallback, useReducer, useRef } from 'react'
import { useSseContext } from '@/contexts/sse-context'
import { isTestMode } from '@/lib/config/test-mode'
import { emitTestEvent } from '@/lib/test/event-emitter'
import { TestEventKind, type ListLoadingTestEvent } from '@/lib/test/test-events'

// UI domain model (camelCase) - log entry
export interface LogEntry {
  message: string
  timestamp: string
}

// API response shape (snake_case) for the initial history fetch
interface DeviceLogsApiResponse {
  logs: Array<{ message: string; timestamp: string }>
  has_more: boolean
  window_start: string | null
  window_end: string | null
}

/**
 * SSE event payload for device-logs events.
 * The gateway sends `@timestamp` (with @ prefix) whereas the REST API uses `timestamp`.
 */
interface SseDeviceLogsPayload {
  device_entity_id: string
  logs: Array<{
    entity_id: string
    message: string
    '@timestamp': string
  }>
}

// Hook state interface
export interface UseDeviceLogsState {
  logs: LogEntry[]
  isLoading: boolean
  hasEntityId: boolean
  isStreaming: boolean
}

// Hook return type
export type UseDeviceLogsResult = UseDeviceLogsState

// Buffer cap increased from 1000 to 5000 per plan
const MAX_BUFFER_SIZE = 5000

/**
 * Combined state managed by a single reducer to avoid cascading setState calls.
 * The reducer handles logs buffer, loading status, and streaming flag together.
 */
interface LogsState {
  logs: LogEntry[]
  isLoading: boolean
  isStreaming: boolean
}

type LogsAction =
  | { type: 'RESET' }
  | { type: 'START_LOADING' }
  | { type: 'SET'; logs: LogEntry[] }
  | { type: 'LOADED' }
  | { type: 'APPEND'; logs: LogEntry[] }
  | { type: 'STREAMING' }

const initialState: LogsState = {
  logs: [],
  isLoading: false,
  isStreaming: false,
}

function logsReducer(state: LogsState, action: LogsAction): LogsState {
  switch (action.type) {
    case 'RESET':
      return initialState
    case 'START_LOADING':
      return { ...state, isLoading: true, isStreaming: false }
    case 'SET': {
      // Atomic replace with cap enforcement
      const logs = action.logs.length > MAX_BUFFER_SIZE
        ? action.logs.slice(action.logs.length - MAX_BUFFER_SIZE)
        : action.logs
      return { ...state, logs }
    }
    case 'LOADED':
      return { ...state, isLoading: false }
    case 'APPEND': {
      const combined = [...state.logs, ...action.logs]
      const logs = combined.length > MAX_BUFFER_SIZE
        ? combined.slice(combined.length - MAX_BUFFER_SIZE)
        : combined
      return { ...state, logs }
    }
    case 'STREAMING':
      return { ...state, isStreaming: true }
    default:
      return state
  }
}

interface UseDeviceLogsOptions {
  /** Device ID for fetching logs and subscribing */
  deviceId: number | undefined
  /** Device entity ID - logs are only available if this is set */
  deviceEntityId: string | undefined
}

/**
 * Custom hook for SSE-driven device log streaming.
 *
 * Lifecycle:
 * 1. Register SSE event listener for "device-logs" events (queue while loading).
 * 2. Subscribe via POST /api/device-logs/subscribe.
 * 3. Fetch initial history via GET /api/devices/{id}/logs (up to 1000 entries).
 * 4. Render history atomically with SET action.
 * 5. Flush queued SSE events newer than the last loaded timestamp.
 * 6. Switch to direct-append streaming mode.
 * 7. On unmount: remove listener, unsubscribe (best-effort).
 */
export function useDeviceLogs({
  deviceId,
  deviceEntityId,
}: UseDeviceLogsOptions): UseDeviceLogsResult {
  const [state, dispatch] = useReducer(logsReducer, initialState)

  const hasEntityId = Boolean(deviceEntityId && deviceEntityId.trim() !== '')

  const { requestId, addEventListener } = useSseContext()

  // Reset logs when device changes -- dispatching a single action avoids cascading renders
  useEffect(() => {
    dispatch({ type: 'RESET' })
  }, [deviceId])

  // Emit instrumentation events in test mode
  const emitLoadingEvent = useCallback(
    (phase: 'loading' | 'ready', logCount: number) => {
      if (!isTestMode() || deviceId === undefined) return

      const payload: Omit<ListLoadingTestEvent, 'timestamp'> = {
        kind: TestEventKind.LIST_LOADING,
        scope: 'devices.logs',
        phase,
        metadata: {
          deviceId,
          logCount,
        },
      }
      emitTestEvent(payload)
    },
    [deviceId]
  )

  // Abort controller for pending unsubscribe calls. When StrictMode causes
  // double-mount, the cleanup's fire-and-forget unsubscribe can race with the
  // re-mount's subscribe. This ref lets the new effect invocation cancel any
  // pending unsubscribe before it reaches the backend.
  const pendingUnsubscribeRef = useRef<AbortController | null>(null)

  // Main SSE subscription effect
  useEffect(() => {
    // Cancel any pending unsubscribe from a previous cleanup (StrictMode)
    pendingUnsubscribeRef.current?.abort()
    pendingUnsubscribeRef.current = null

    if (!hasEntityId || deviceId === undefined || !requestId) {
      return
    }

    let isMounted = true
    let abortController: AbortController | null = null
    // Queue for SSE events arriving before the initial fetch completes
    const eventQueue: LogEntry[] = []
    let isStreamingDirect = false
    let cutoffTimestamp: string | null = null

    // Track emitted ready to avoid duplicates
    let hasEmittedReady = false

    dispatch({ type: 'START_LOADING' })
    emitLoadingEvent('loading', 0)

    // 1. Register SSE event listener -- queue events until streaming switches on
    const removeListener = addEventListener('device-logs', (data: unknown) => {
      const payload = data as SseDeviceLogsPayload
      // Only process events for our device
      if (payload.device_entity_id !== deviceEntityId) return

      const entries: LogEntry[] = payload.logs.map((log) => ({
        message: log.message,
        timestamp: log['@timestamp'],
      }))

      if (isStreamingDirect) {
        // Direct append mode -- events go straight into the buffer
        dispatch({ type: 'APPEND', logs: entries })
      } else {
        // Queuing mode -- buffer until history is loaded and flushed
        eventQueue.push(...entries)
      }
    })

    // 2. Subscribe to the device log stream on the backend
    const subscribe = async (): Promise<boolean> => {
      abortController = new AbortController()
      try {
        const response = await fetch('/api/device-logs/subscribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ request_id: requestId, device_id: deviceId }),
          signal: abortController.signal,
          credentials: 'include',
        })
        return response.ok
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') return false
        console.debug('[useDeviceLogs] Subscribe failed:', error)
        return false
      }
    }

    // 3. Fetch initial log history
    const fetchHistory = async (): Promise<{
      logs: LogEntry[]
      windowEnd: string | null
    } | null> => {
      abortController = new AbortController()
      try {
        const url = new URL(`/api/devices/${deviceId}/logs`, window.location.origin)

        const response = await fetch(url.toString(), {
          signal: abortController.signal,
          credentials: 'include',
        })

        if (!response.ok) {
          console.debug(`[useDeviceLogs] History fetch failed: ${response.status}`)
          return null
        }

        const data: DeviceLogsApiResponse = await response.json()
        const historyLogs: LogEntry[] = data.logs.map((log) => ({
          message: log.message,
          timestamp: log.timestamp,
        }))

        return { logs: historyLogs, windowEnd: data.window_end }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') return null
        console.debug('[useDeviceLogs] History fetch error:', error)
        return null
      }
    }

    // Orchestrate the subscribe -> fetch -> flush -> stream lifecycle
    const run = async () => {
      // Subscribe
      const subscribed = await subscribe()
      if (!isMounted) return

      if (!subscribed) {
        // Subscription failed -- show empty state
        dispatch({ type: 'LOADED' })
        if (!hasEmittedReady) {
          hasEmittedReady = true
          emitLoadingEvent('ready', 0)
        }
        return
      }

      // Fetch initial history
      const history = await fetchHistory()
      if (!isMounted) return

      const initialLogs = history?.logs ?? []
      const windowEnd = history?.windowEnd ?? null

      // 4. Atomically render history
      dispatch({ type: 'SET', logs: initialLogs })

      // Record the cutoff timestamp for deduplication during flush
      if (initialLogs.length > 0) {
        cutoffTimestamp = initialLogs[initialLogs.length - 1].timestamp
      } else if (windowEnd) {
        cutoffTimestamp = windowEnd
      }

      dispatch({ type: 'LOADED' })

      // Emit ready event
      if (!hasEmittedReady) {
        hasEmittedReady = true
        emitLoadingEvent('ready', initialLogs.length)
      }

      // 5. Flush queued SSE events that arrived during the loading phase
      const queuedToFlush = cutoffTimestamp
        ? eventQueue.filter((entry) => entry.timestamp > cutoffTimestamp!)
        : [...eventQueue]

      if (queuedToFlush.length > 0) {
        dispatch({ type: 'APPEND', logs: queuedToFlush })
      }

      // 6. Switch to direct-append streaming mode
      isStreamingDirect = true
      if (isMounted) {
        dispatch({ type: 'STREAMING' })
      }
    }

    run()

    // 7. Cleanup: remove listener, unsubscribe (best-effort)
    return () => {
      isMounted = false
      removeListener()
      abortController?.abort()

      // Best-effort unsubscribe -- abortable so StrictMode re-mount can cancel it.
      // keepalive is omitted intentionally: when the page actually closes, the SSE
      // disconnect callback will clean up subscriptions on the backend.
      const unsubscribeController = new AbortController()
      pendingUnsubscribeRef.current = unsubscribeController
      fetch('/api/device-logs/unsubscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_id: requestId, device_id: deviceId }),
        credentials: 'include',
        signal: unsubscribeController.signal,
      }).catch(() => {
        // Swallow -- best-effort cleanup (includes AbortError from StrictMode cancel)
      })
    }
  }, [deviceId, deviceEntityId, hasEntityId, requestId, addEventListener, emitLoadingEvent])

  return {
    logs: state.logs,
    isLoading: state.isLoading,
    hasEntityId,
    isStreaming: state.isStreaming,
  }
}
