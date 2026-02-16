import { useRef, useEffect, useCallback, useState } from 'react'
import { useDeviceLogs } from '@/hooks/use-device-logs'

interface DeviceLogsViewerProps {
  /** Device ID for fetching logs */
  deviceId: number
  /** Device entity ID from config - logs only shown if this is set */
  deviceEntityId: string | undefined
  /** When true, the viewer fills the available parent height instead of using a fixed height */
  fullHeight?: boolean
}

// Threshold in pixels for determining if scroll is "at bottom"
const SCROLL_THRESHOLD_PX = 10

// Approximate height for 30 lines of monospace text (30 lines * ~20px line height)
const VIEWER_HEIGHT = '480px'

/**
 * Terminal-style log viewer component for displaying device logs.
 *
 * Features:
 * - Terminal styling with dark background and monospace font
 * - Connected/Disconnected status indicator for SSE streaming
 * - Auto-scroll only when already at bottom
 * - Hidden when device has no entity_id; shows "No logs available" when empty
 */
export function DeviceLogsViewer({ deviceId, deviceEntityId, fullHeight }: DeviceLogsViewerProps) {
  const {
    logs,
    isLoading,
    hasEntityId,
    isStreaming,
  } = useDeviceLogs({
    deviceId,
    deviceEntityId,
  })

  // Track whether scroll is at bottom (for UI display via data attribute)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // Use a ref to track scroll position for auto-scroll decisions to avoid stale state
  const wasAtBottomRef = useRef(true)
  // Guard flag: prevents onScroll events fired during programmatic scrollTop
  // assignments from incorrectly clearing wasAtBottomRef when new content has
  // already increased scrollHeight before the scroll event is delivered.
  const isAutoScrollingRef = useRef(false)

  // Check if scroll is at bottom
  const checkIsAtBottom = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return true

    const { scrollTop, scrollHeight, clientHeight } = container
    return scrollHeight - scrollTop - clientHeight <= SCROLL_THRESHOLD_PX
  }, [])

  // Handle scroll events to track position.
  // Ignores events triggered by programmatic auto-scroll to avoid race
  // conditions where rapid log batches increase scrollHeight between the
  // scrollTop assignment and the scroll event delivery.
  const handleScroll = useCallback(() => {
    if (isAutoScrollingRef.current) return
    const atBottom = checkIsAtBottom()
    setIsAtBottom(atBottom)
    wasAtBottomRef.current = atBottom
  }, [checkIsAtBottom])

  // Auto-scroll to bottom when new logs arrive (only if already at bottom)
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    if (wasAtBottomRef.current) {
      isAutoScrollingRef.current = true
      container.scrollTop = container.scrollHeight
      // Clear the guard after scroll events from this update settle.
      // requestAnimationFrame fires after any synchronously-dispatched scroll
      // events and before the next frame, covering both delivery timings.
      requestAnimationFrame(() => {
        isAutoScrollingRef.current = false
      })
    }
  }, [logs])

  // Don't render if no entity ID
  if (!hasEntityId) {
    return null
  }

  return (
    <div data-testid="devices.logs.viewer" className={fullHeight ? 'flex flex-col flex-1 min-h-0 gap-2' : 'space-y-2'}>
      {/* Header with label and streaming status */}
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-muted-foreground">
          Device Logs
        </label>
        <span
          className={`flex items-center gap-1.5 text-xs font-medium ${
            isStreaming ? 'text-green-500' : 'text-muted-foreground'
          }`}
          data-testid="devices.logs.streaming-status"
          data-streaming={isStreaming ? 'true' : 'false'}
        >
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              isStreaming ? 'bg-green-500' : 'bg-muted-foreground'
            }`}
          />
          {isStreaming ? 'Connected' : 'Connecting...'}
        </span>
      </div>

      {/* Log container with terminal styling */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        style={fullHeight ? undefined : { height: VIEWER_HEIGHT }}
        className={`overflow-auto rounded-md border border-border bg-gray-900 p-4 font-mono text-sm text-gray-200${fullHeight ? ' flex-1 min-h-0' : ''}`}
        data-testid="devices.logs.container"
        data-scroll-at-bottom={isAtBottom ? 'true' : 'false'}
      >
        {isLoading && logs.length === 0 ? (
          <div className="text-gray-500">Loading logs...</div>
        ) : logs.length === 0 ? (
          <div className="text-gray-500">No logs available</div>
        ) : (
          logs.map((log, index) => (
            <div
              key={`${log.timestamp}-${index}`}
              className="whitespace-pre-wrap break-all leading-relaxed"
              data-testid="devices.logs.entry"
              title={new Date(log.timestamp).toLocaleString()}
            >
              {log.message}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
