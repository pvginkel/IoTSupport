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
 * - Right-aligned checkbox to toggle live updates (default checked)
 * - Auto-scroll only when already at bottom
 * - Hidden when device has no entity_id; shows "No logs available" when empty
 */
export function DeviceLogsViewer({ deviceId, deviceEntityId, fullHeight }: DeviceLogsViewerProps) {
  const {
    logs,
    isLoading,
    hasEntityId,
    isPolling,
    startPolling,
    stopPolling
  } = useDeviceLogs({
    deviceId,
    deviceEntityId,
    defaultPolling: true
  })

  // Track whether scroll is at bottom (for UI display via data attribute)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // Use a ref to track scroll position for auto-scroll decisions to avoid stale state
  const wasAtBottomRef = useRef(true)

  // Check if scroll is at bottom
  const checkIsAtBottom = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return true

    const { scrollTop, scrollHeight, clientHeight } = container
    return scrollHeight - scrollTop - clientHeight <= SCROLL_THRESHOLD_PX
  }, [])

  // Handle scroll events to track position
  const handleScroll = useCallback(() => {
    const atBottom = checkIsAtBottom()
    setIsAtBottom(atBottom)
    wasAtBottomRef.current = atBottom
  }, [checkIsAtBottom])

  // Auto-scroll to bottom when new logs arrive (only if already at bottom)
  // Uses ref to get fresh scroll position, avoiding stale state during rapid updates
  useEffect(() => {
    const container = scrollContainerRef.current
    if (!container) return

    // Check scroll position directly to handle rapid log batches correctly
    // The ref captures the position before new logs were appended
    if (wasAtBottomRef.current) {
      container.scrollTop = container.scrollHeight
      // Keep ref in sync - state will update via onScroll handler
      wasAtBottomRef.current = true
    }
  }, [logs])

  // Handle checkbox toggle
  const handleLiveToggle = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.checked) {
      startPolling()
    } else {
      stopPolling()
    }
  }, [startPolling, stopPolling])

  // Don't render if no entity ID
  if (!hasEntityId) {
    return null
  }

  return (
    <div data-testid="devices.logs.viewer" className={fullHeight ? 'flex flex-col flex-1 min-h-0 gap-2' : 'space-y-2'}>
      {/* Header with label and checkbox */}
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-muted-foreground">
          Device Logs
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
          <span>Live Updates</span>
          <input
            type="checkbox"
            checked={isPolling}
            onChange={handleLiveToggle}
            className="h-4 w-4 rounded border-border bg-background text-primary focus:ring-primary focus:ring-offset-background"
            data-testid="devices.logs.live-checkbox"
          />
        </label>
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
