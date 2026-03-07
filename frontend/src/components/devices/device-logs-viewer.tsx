import { useRef, useEffect, useLayoutEffect, useCallback, useState } from 'react'
import { Download } from 'lucide-react'
import { useDeviceLogs } from '@/hooks/use-device-logs'
import { DeviceLogsDownloadDialog } from './device-logs-download-dialog'

interface DeviceLogsViewerProps {
  /** Device ID for fetching logs */
  deviceId: number
  /** Device entity ID from config - logs only shown if this is set */
  deviceEntityId: string | undefined
  /** Device name used in download filenames */
  deviceName: string
  /** When true, the viewer fills the available parent height instead of using a fixed height */
  fullHeight?: boolean
}

// Threshold in pixels for determining if scroll is "at bottom" or "at top"
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
 * - Scroll-to-top triggers backward pagination (infinite scroll)
 * - Download button opens dialog for fetching and saving logs as a file
 * - Hidden when device has no entity_id; shows "No logs available" when empty
 */
export function DeviceLogsViewer({ deviceId, deviceEntityId, deviceName, fullHeight }: DeviceLogsViewerProps) {
  const {
    logs,
    isLoading,
    hasEntityId,
    hasMore,
    prependCounter,
    fetchOlderLogs,
    isFetchingOlder,
  } = useDeviceLogs({
    deviceId,
    deviceEntityId,
  })

  // Track whether scroll is at bottom/top (for UI display via data attributes)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const [isAtTop, setIsAtTop] = useState(false)
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false)
  const scrollContainerRef = useRef<HTMLDivElement>(null)
  // Use a ref to track scroll position for auto-scroll decisions to avoid stale state
  const wasAtBottomRef = useRef(true)
  // Guard flag: prevents onScroll events fired during programmatic scrollTop
  // assignments from incorrectly clearing wasAtBottomRef when new content has
  // already increased scrollHeight before the scroll event is delivered.
  const isAutoScrollingRef = useRef(false)
  // Store scrollHeight before a backfill fetch for position restoration
  const previousScrollHeightRef = useRef<number>(0)

  // Refs that track values consumed by handleScroll so it remains stable
  const fetchOlderLogsRef = useRef(fetchOlderLogs)
  const hasMoreRef = useRef(hasMore)
  const isFetchingOlderRef = useRef(isFetchingOlder)
  useEffect(() => { fetchOlderLogsRef.current = fetchOlderLogs }, [fetchOlderLogs])
  useEffect(() => { hasMoreRef.current = hasMore }, [hasMore])
  useEffect(() => { isFetchingOlderRef.current = isFetchingOlder }, [isFetchingOlder])

  // Check if scroll is at bottom
  const checkIsAtBottom = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return true

    const { scrollTop, scrollHeight, clientHeight } = container
    return scrollHeight - scrollTop - clientHeight <= SCROLL_THRESHOLD_PX
  }, [])

  // Check if scroll is at top
  const checkIsAtTop = useCallback(() => {
    const container = scrollContainerRef.current
    if (!container) return false

    return container.scrollTop <= SCROLL_THRESHOLD_PX
  }, [])

  // Handle scroll events to track position and trigger backfill.
  // Reads backfill state from refs so the handler identity is stable and
  // doesn't cause the onScroll listener to be reattached on every log append.
  const handleScroll = useCallback(() => {
    if (isAutoScrollingRef.current) return
    const atBottom = checkIsAtBottom()
    const atTop = checkIsAtTop()
    setIsAtBottom(atBottom)
    setIsAtTop(atTop)
    wasAtBottomRef.current = atBottom

    // Trigger backfill when scrolled to top, if conditions allow
    if (atTop && hasMoreRef.current && !isFetchingOlderRef.current) {
      // Record scrollHeight before fetch for position restoration
      const container = scrollContainerRef.current
      if (container) {
        previousScrollHeightRef.current = container.scrollHeight
      }
      void fetchOlderLogsRef.current()
    }
  }, [checkIsAtBottom, checkIsAtTop])

  // Restore scroll position after prepend (before browser paints)
  // keyed on prependCounter so it only fires after a PREPEND dispatch
  useLayoutEffect(() => {
    if (prependCounter === 0) return
    const container = scrollContainerRef.current
    if (!container) return

    const previousHeight = previousScrollHeightRef.current
    if (previousHeight === 0) return

    const delta = container.scrollHeight - previousHeight
    if (delta > 0) {
      isAutoScrollingRef.current = true
      container.scrollTop += delta
      requestAnimationFrame(() => {
        isAutoScrollingRef.current = false
      })
    }
    // Reset for next prepend
    previousScrollHeightRef.current = 0
  }, [prependCounter])

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
      {/* Header with label and download button */}
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-muted-foreground">
          Device Logs
        </label>
        <button
          type="button"
          onClick={() => setDownloadDialogOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-md px-2 h-7 text-sm cursor-pointer text-muted-foreground hover:text-foreground hover:bg-secondary"
          data-testid="devices.logs.download-button"
          title="Download logs"
        >
          <Download className="h-4 w-4" />
          Download
        </button>
      </div>

      {/* Log container with terminal styling */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        style={fullHeight ? undefined : { height: VIEWER_HEIGHT }}
        className={`overflow-auto rounded-md border border-border bg-gray-900 p-4 font-mono text-sm text-gray-200${fullHeight ? ' flex-1 min-h-0' : ''}`}
        data-testid="devices.logs.container"
        data-scroll-at-bottom={isAtBottom ? 'true' : 'false'}
        data-scroll-at-top={isAtTop ? 'true' : 'false'}
        data-log-count={logs.length}
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

      {/* Download dialog */}
      <DeviceLogsDownloadDialog
        open={downloadDialogOpen}
        onOpenChange={setDownloadDialogOpen}
        deviceId={deviceId}
        deviceName={deviceName}
      />
    </div>
  )
}
