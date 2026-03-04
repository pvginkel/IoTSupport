import { useState, useCallback, useRef, useEffect } from 'react'
import {
  Dialog,
  DialogInnerContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/primitives/dialog'
import { Button } from '@/components/primitives/button'
import { fetchLogsForDownload } from '@/hooks/use-device-logs'

interface DeviceLogsDownloadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  deviceId: number
  deviceName: string
}

/** Available line-count options for download */
const LINE_COUNT_OPTIONS = [100, 500, 1000, 5000, 10000] as const

type DownloadState =
  | { phase: 'selecting' }
  | { phase: 'fetching'; fetched: number; total: number }
  | { phase: 'complete' }
  | { phase: 'error'; message: string }

/**
 * Sanitize a device name for use in filenames.
 * Replaces non-alphanumeric characters (except hyphens) with hyphens,
 * collapses consecutive hyphens, and trims leading/trailing hyphens.
 */
function sanitizeDeviceName(name: string): string {
  return name
    .replace(/[^a-zA-Z0-9-]/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '')
    || 'unknown'
}

/**
 * Build a download filename from device name and current timestamp.
 * Pattern: device-{name}-logs-{timestamp}.log
 */
function buildFilename(deviceName: string): string {
  const sanitized = sanitizeDeviceName(deviceName)
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
  return `device-${sanitized}-logs-${timestamp}.log`
}

/**
 * Trigger a browser download of a text file.
 */
function triggerDownload(content: string, filename: string): void {
  const blob = new Blob([content], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

/**
 * Download dialog for device logs.
 *
 * Presents line-count options (100, 500, 1000, 5000, 10000).
 * On confirmation, fetches logs via sequential paginated API calls,
 * builds a plain text file with raw messages (one per line, no timestamps),
 * and triggers a browser download.
 *
 * Cancellation: closing the dialog mid-fetch aborts in-flight requests
 * via AbortController.
 */
export function DeviceLogsDownloadDialog({
  open,
  onOpenChange,
  deviceId,
  deviceName,
}: DeviceLogsDownloadDialogProps) {
  const [selectedCount, setSelectedCount] = useState<number>(1000)
  const [downloadState, setDownloadState] = useState<DownloadState>({ phase: 'selecting' })
  const abortControllerRef = useRef<AbortController | null>(null)
  const autoCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Wrap onOpenChange to reset state on open and abort on close
  const handleOpenChange = useCallback((nextOpen: boolean) => {
    if (nextOpen) {
      // Reset to initial selection state when opening
      setDownloadState({ phase: 'selecting' })
      setSelectedCount(1000)
    } else {
      // Abort in-flight requests and clear auto-close timer when closing
      abortControllerRef.current?.abort()
      abortControllerRef.current = null
      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current)
        autoCloseTimerRef.current = null
      }
    }
    onOpenChange(nextOpen)
  }, [onOpenChange])

  // Abort and clean up on unmount as a safety net
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current)
      }
    }
  }, [])

  const handleDownload = useCallback(async () => {
    const controller = new AbortController()
    abortControllerRef.current = controller

    setDownloadState({ phase: 'fetching', fetched: 0, total: selectedCount })

    try {
      const logs = await fetchLogsForDownload(
        deviceId,
        selectedCount,
        (fetched, total) => {
          setDownloadState({ phase: 'fetching', fetched, total })
        },
        controller.signal,
      )

      if (controller.signal.aborted) return

      // Build plain text content -- raw messages only, one per line
      const content = logs.map((log) => log.message).join('\n')
      const filename = buildFilename(deviceName)
      triggerDownload(content, filename)

      setDownloadState({ phase: 'complete' })

      // Auto-close after a short delay
      autoCloseTimerRef.current = setTimeout(() => {
        autoCloseTimerRef.current = null
        if (!controller.signal.aborted) {
          handleOpenChange(false)
        }
      }, 500)
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return
      setDownloadState({
        phase: 'error',
        message: error instanceof Error ? error.message : 'Download failed',
      })
    }
  }, [deviceId, deviceName, selectedCount, handleOpenChange])

  const isSelecting = downloadState.phase === 'selecting'
  const isFetching = downloadState.phase === 'fetching'
  const isError = downloadState.phase === 'error'

  return (
    <Dialog
      open={open}
      onOpenChange={handleOpenChange}
      contentProps={{ 'data-testid': 'devices.logs.download-dialog' }}
    >
      <DialogInnerContent>
        <DialogHeader>
          <DialogTitle>Download Logs</DialogTitle>
          <DialogDescription>
            Select the number of log lines to download.
          </DialogDescription>
        </DialogHeader>

        {/* Line count options */}
        {isSelecting && (
          <div className="grid grid-cols-5 gap-2">
            {LINE_COUNT_OPTIONS.map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => setSelectedCount(count)}
                data-testid={`devices.logs.download-dialog.option-${count}`}
                className={`rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                  selectedCount === count
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-secondary/50 text-muted-foreground hover:bg-secondary'
                }`}
              >
                {count.toLocaleString()}
              </button>
            ))}
          </div>
        )}

        {/* Progress indicator during fetch */}
        {isFetching && (
          <div className="flex items-center gap-3 py-2">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span className="text-sm text-muted-foreground">
              Fetching logs... {downloadState.fetched.toLocaleString()} / {downloadState.total.toLocaleString()}
            </span>
          </div>
        )}

        {/* Error state */}
        {isError && (
          <div className="rounded-md border border-red-800 bg-red-900/20 p-3">
            <p className="text-sm text-red-400">{downloadState.message}</p>
          </div>
        )}

        {/* Complete state */}
        {downloadState.phase === 'complete' && (
          <div className="py-2">
            <p className="text-sm text-green-400">Download started.</p>
          </div>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => handleOpenChange(false)}
          >
            {isFetching ? 'Cancel' : 'Close'}
          </Button>
          {(isSelecting || isError) && (
            <Button
              variant="primary"
              onClick={() => void handleDownload()}
              data-testid="devices.logs.download-dialog.submit"
            >
              Download
            </Button>
          )}
        </DialogFooter>
      </DialogInnerContent>
    </Dialog>
  )
}
