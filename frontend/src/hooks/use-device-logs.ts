import { useEffect, useCallback, useReducer, useRef, useState } from 'react'
import { useSseContext } from '@/contexts/sse-context'
import { isTestMode } from '@/lib/config/test-mode'
import { emitTestEvent } from '@/lib/test/event-emitter'
import { TestEventKind, type ListLoadingTestEvent } from '@/lib/test/test-events'

// UI domain model (camelCase) - log entry
interface LogEntry {
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

// Hook state interface -- extends reducer state with entity presence flag
interface UseDeviceLogsState {
  logs: LogEntry[]
  isLoading: boolean
  hasEntityId: boolean
  isStreaming: boolean
  hasMore: boolean
  oldestTimestamp: string | null
  prependCounter: number
}

// Hook return type -- includes backfill controls
type UseDeviceLogsResult = UseDeviceLogsState & {
  fetchOlderLogs: () => Promise<void>
  isFetchingOlder: boolean
}

// Buffer cap raised from 5,000 to 10,000 for backfill support
const MAX_BUFFER_SIZE = 10000

/**
 * Combined state managed by a single reducer to avoid cascading setState calls.
 * The reducer handles logs buffer, loading status, streaming flag, and backfill
 * pagination state (hasMore, oldestTimestamp) together.
 */
interface LogsState {
  logs: LogEntry[]
  isLoading: boolean
  isStreaming: boolean
  hasMore: boolean
  oldestTimestamp: string | null
  /** Incremented on each PREPEND dispatch so the viewer can key a useLayoutEffect for scroll restoration */
  prependCounter: number
}

type LogsAction =
  | { type: 'RESET' }
  | { type: 'START_LOADING' }
  | { type: 'SET'; logs: LogEntry[]; hasMore: boolean; oldestTimestamp: string | null }
  | { type: 'LOADED' }
  | { type: 'APPEND'; logs: LogEntry[] }
  | { type: 'PREPEND'; logs: LogEntry[]; hasMore: boolean; oldestTimestamp: string | null }
  | { type: 'STREAMING' }

const initialState: LogsState = {
  logs: [],
  isLoading: false,
  isStreaming: false,
  hasMore: false,
  oldestTimestamp: null,
  prependCounter: 0,
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
      return {
        ...state,
        logs,
        hasMore: action.hasMore,
        oldestTimestamp: action.oldestTimestamp,
      }
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
    case 'PREPEND': {
      // Prepend older entries to the front of the buffer
      const combined = [...action.logs, ...state.logs]
      // If combined would exceed cap, refuse the prepend to preserve streaming tail
      if (combined.length > MAX_BUFFER_SIZE) {
        return {
          ...state,
          hasMore: false,
        }
      }
      return {
        ...state,
        logs: combined,
        hasMore: action.hasMore,
        oldestTimestamp: action.oldestTimestamp,
        prependCounter: state.prependCounter + 1,
      }
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
 * Custom hook for SSE-driven device log streaming with backward pagination.
 *
 * Lifecycle:
 * 1. Register SSE event listener for "device-logs" events (queue while loading).
 * 2. Subscribe via POST /api/device-logs/subscribe.
 * 3. Fetch initial history via GET /api/devices/{id}/logs (up to 1000 entries).
 * 4. Render history atomically with SET action.
 * 5. Flush queued SSE events newer than the last loaded timestamp.
 * 6. Switch to direct-append streaming mode.
 * 7. On unmount: remove listener, unsubscribe (best-effort).
 *
 * Backfill:
 * - Exposes fetchOlderLogs() for the viewer to call on scroll-to-top.
 * - Fetches one page of older logs using `end=oldestTimestamp` and dispatches PREPEND.
 * - Guards against concurrent fetches and buffer overflow.
 */
export function useDeviceLogs({
  deviceId,
  deviceEntityId,
}: UseDeviceLogsOptions): UseDeviceLogsResult {
  const [state, dispatch] = useReducer(logsReducer, initialState)

  const hasEntityId = Boolean(deviceEntityId && deviceEntityId.trim() !== '')

  const { requestId, addEventListener } = useSseContext()

  // Ref to guard against concurrent backfill fetches, paired with state for re-renders
  const isFetchingOlderRef = useRef(false)
  const [isFetchingOlder, setIsFetchingOlder] = useState(false)

  // Refs that track state values consumed by fetchOlderLogs to keep it stable
  const hasMoreRef = useRef(state.hasMore)
  const oldestTimestampRef = useRef(state.oldestTimestamp)
  const logsLengthRef = useRef(state.logs.length)
  useEffect(() => { hasMoreRef.current = state.hasMore }, [state.hasMore])
  useEffect(() => { oldestTimestampRef.current = state.oldestTimestamp }, [state.oldestTimestamp])
  useEffect(() => { logsLengthRef.current = state.logs.length }, [state.logs.length])

  // AbortController for in-flight backfill requests -- aborted on device change/unmount
  const backfillAbortRef = useRef<AbortController | null>(null)

  // Reset logs when device changes -- dispatching a single action avoids cascading renders
  useEffect(() => {
    dispatch({ type: 'RESET' })
    isFetchingOlderRef.current = false
    setIsFetchingOlder(false)
    backfillAbortRef.current?.abort()
    backfillAbortRef.current = null
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

  // Main effect: fetch history (always) and optionally set up SSE streaming.
  // History fetching only depends on deviceId + hasEntityId.
  // SSE streaming additionally requires requestId from the SSE context.
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

    // 3. Fetch initial log history using backward pagination from a future
    //    cursor. This reuses the same code path as backfill, so `has_more`
    //    directly indicates whether older entries exist.
    const fetchHistory = async (): Promise<{
      logs: LogEntry[]
      hasMore: boolean
      windowStart: string | null
      windowEnd: string | null
    } | null> => {
      abortController = new AbortController()
      try {
        const url = new URL(`/api/devices/${deviceId}/logs`, window.location.origin)
        // Use a date one day in the future to ensure we capture all recent entries
        // eslint-disable-next-line no-restricted-properties -- Real timestamp for API cursor, not ID generation
        const futureEnd = new Date(Date.now() + 86_400_000).toISOString()
        url.searchParams.set('end', futureEnd)

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

        return {
          logs: historyLogs,
          hasMore: data.has_more,
          windowStart: data.window_start,
          windowEnd: data.window_end,
        }
      } catch (error) {
        if (error instanceof Error && error.name === 'AbortError') return null
        console.debug('[useDeviceLogs] History fetch error:', error)
        return null
      }
    }

    // Orchestrate the subscribe -> fetch -> flush -> stream lifecycle.
    // History is always fetched regardless of SSE subscribe result, so
    // historical logs are visible even without a streaming connection.
    const run = async () => {
      // Subscribe (best-effort — streaming is a bonus, not a prerequisite)
      const subscribed = await subscribe()
      if (!isMounted) return

      // Fetch initial history regardless of subscribe outcome
      const history = await fetchHistory()
      if (!isMounted) return

      const initialLogs = history?.logs ?? []
      const hasMore = history?.hasMore ?? false
      const windowStart = history?.windowStart ?? null
      const windowEnd = history?.windowEnd ?? null

      // 4. Atomically render history with pagination metadata
      dispatch({
        type: 'SET',
        logs: initialLogs,
        hasMore,
        oldestTimestamp: windowStart,
      })

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

      // If subscribe failed, skip the streaming setup
      if (!subscribed) return

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

  /**
   * Fetch one page of older logs for backward pagination (infinite scroll).
   *
   * Guards:
   * - Skips if already fetching, no more pages, no oldest timestamp, or buffer at capacity.
   * - Uses isFetchingOlderRef to prevent concurrent calls.
   */
  // Reads from refs so the callback identity only changes with deviceId,
  // preventing handleScroll from being recreated on every log append.
  const fetchOlderLogs = useCallback(async () => {
    if (
      isFetchingOlderRef.current ||
      !hasMoreRef.current ||
      !oldestTimestampRef.current ||
      deviceId === undefined ||
      logsLengthRef.current >= MAX_BUFFER_SIZE
    ) {
      return
    }

    isFetchingOlderRef.current = true
    setIsFetchingOlder(true)

    const controller = new AbortController()
    backfillAbortRef.current = controller

    try {
      const url = new URL(`/api/devices/${deviceId}/logs`, window.location.origin)
      url.searchParams.set('end', oldestTimestampRef.current)

      const response = await fetch(url.toString(), {
        credentials: 'include',
        signal: controller.signal,
      })

      if (!response.ok) {
        console.debug(`[useDeviceLogs] Backfill fetch failed: ${response.status}`)
        return
      }

      const data: DeviceLogsApiResponse = await response.json()
      const olderLogs: LogEntry[] = data.logs.map((log) => ({
        message: log.message,
        timestamp: log.timestamp,
      }))

      if (olderLogs.length > 0) {
        dispatch({
          type: 'PREPEND',
          logs: olderLogs,
          hasMore: data.has_more,
          oldestTimestamp: data.window_start,
        })
      } else {
        // No entries returned -- mark as exhausted
        dispatch({
          type: 'PREPEND',
          logs: [],
          hasMore: false,
          oldestTimestamp: oldestTimestampRef.current,
        })
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return
      console.debug('[useDeviceLogs] Backfill fetch error:', error)
    } finally {
      isFetchingOlderRef.current = false
      setIsFetchingOlder(false)
      backfillAbortRef.current = null
    }
  }, [deviceId])

  return {
    logs: state.logs,
    isLoading: state.isLoading,
    hasEntityId,
    isStreaming: state.isStreaming,
    hasMore: state.hasMore,
    oldestTimestamp: state.oldestTimestamp,
    prependCounter: state.prependCounter,
    fetchOlderLogs,
    isFetchingOlder,
  }
}

/**
 * Fetch device logs for download (independent of the hook's buffer).
 *
 * Performs sequential paginated API calls backward from `now`, collecting up to
 * `lineCount` entries. Returns the collected log messages in chronological order.
 *
 * @param deviceId - Device ID to fetch logs for
 * @param lineCount - Maximum number of log lines to collect
 * @param onProgress - Callback with (fetched, total) for progress reporting
 * @param signal - AbortSignal for cancellation
 */
export async function fetchLogsForDownload(
  deviceId: number,
  lineCount: number,
  onProgress?: (fetched: number, total: number) => void,
  signal?: AbortSignal,
): Promise<LogEntry[]> {
  const collected: LogEntry[] = []
  let cursor: string = new Date().toISOString()
  let hasMore = true

  while (hasMore && collected.length < lineCount) {
    if (signal?.aborted) break

    const url = new URL(`/api/devices/${deviceId}/logs`, window.location.origin)
    url.searchParams.set('end', cursor)

    const response = await fetch(url.toString(), {
      credentials: 'include',
      signal,
    })

    if (!response.ok) {
      console.debug(`[fetchLogsForDownload] Fetch failed: ${response.status}`)
      break
    }

    const data: DeviceLogsApiResponse = await response.json()
    const logs: LogEntry[] = data.logs.map((log) => ({
      message: log.message,
      timestamp: log.timestamp,
    }))

    // Collect pages in reverse-chronological order; we reverse at the end
    collected.push(...logs)
    hasMore = data.has_more
    if (data.window_start) {
      cursor = data.window_start
    } else {
      break
    }

    onProgress?.(collected.length, lineCount)
  }

  // Reverse to chronological order (pages were fetched newest-first)
  collected.reverse()

  // Trim to exact requested count (keep the most recent entries)
  if (collected.length > lineCount) {
    return collected.slice(collected.length - lineCount)
  }

  return collected
}
