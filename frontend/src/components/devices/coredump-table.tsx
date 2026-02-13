import { useMemo, useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Trash2, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ConfirmDialog } from '@/components/ui/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useCoredumps, useDeleteCoredump, formatFileSize } from '@/hooks/use-coredumps'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'
import { useFormInstrumentation } from '@/lib/test/form-instrumentation'

interface CoredumpTableProps {
  deviceId: number
}

/**
 * Core dumps table rendered on the device editor page.
 * Always visible (with empty state when no coredumps exist).
 * Rows are clickable to navigate to the coredump detail page.
 */
export function CoredumpTable({ deviceId }: CoredumpTableProps) {
  const navigate = useNavigate()
  const { coredumps, isLoading, isFetching, error } = useCoredumps(deviceId)
  const deleteCoredump = useDeleteCoredump()
  const { confirm, confirmProps } = useConfirm()

  // Form instrumentation for the delete mutation lifecycle
  const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({
    formId: 'CoredumpDelete'
  })

  // List loading instrumentation for Playwright
  useListLoadingInstrumentation({
    scope: 'coredumps.list',
    isLoading,
    isFetching,
    error,
    getReadyMetadata: () => ({ visible: coredumps.length, total: coredumps.length })
  })

  // Sort coredumps by uploadedAt descending (newest first)
  const sortedCoredumps = useMemo(() => {
    return [...coredumps].sort((a, b) =>
      new Date(b.uploadedAt).getTime() - new Date(a.uploadedAt).getTime()
    )
  }, [coredumps])

  const handleDelete = useCallback(async (coredumpId: number, filename: string) => {
    const confirmed = await confirm({
      title: 'Delete Core Dump',
      description: `Delete core dump "${filename}"? This action cannot be undone.`,
      confirmText: 'Delete',
      destructive: true
    })

    if (confirmed) {
      trackSubmit({ deviceId, coredumpId })
      deleteCoredump.mutate(
        { deviceId, coredumpId },
        {
          onSuccess: () => {
            trackSuccess({ deviceId, coredumpId })
          },
          onError: (err) => {
            trackError(err instanceof Error ? err.message : 'Unknown error')
          }
        }
      )
    }
  }, [confirm, deleteCoredump, deviceId, trackSubmit, trackSuccess, trackError])

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="space-y-2" data-testid="coredumps.table">
        <label className="block text-sm font-medium text-muted-foreground">
          Core Dumps
        </label>
        <div className="space-y-2" data-testid="coredumps.table.loading">
          {[...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-2" data-testid="coredumps.table">
        <label className="block text-sm font-medium text-muted-foreground">
          Core Dumps
        </label>
        <div className="text-destructive" data-testid="coredumps.table.error">
          Failed to load core dumps
        </div>
      </div>
    )
  }

  // Empty state
  if (sortedCoredumps.length === 0) {
    return (
      <div className="space-y-2" data-testid="coredumps.table">
        <label className="block text-sm font-medium text-muted-foreground">
          Core Dumps
        </label>
        <EmptyState
          title="No core dumps recorded for this device"
          data-testid="coredumps.table.empty"
        />
      </div>
    )
  }

  return (
    <div className="space-y-2" data-testid="coredumps.table">
      <label className="block text-sm font-medium text-muted-foreground">
        Core Dumps
      </label>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead className="border-b border-border">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Uploaded At</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Firmware</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Size</th>
              <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Status</th>
              <th className="px-4 py-3 text-right text-sm font-semibold text-foreground">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedCoredumps.map((coredump) => (
              <tr
                key={coredump.id}
                className="border-b border-border hover:bg-secondary/50 cursor-pointer"
                data-testid="coredumps.table.row"
                data-coredump-id={coredump.id}
                onClick={() => navigate({
                  to: '/devices/$deviceId/coredumps/$coredumpId',
                  params: { deviceId: String(deviceId), coredumpId: String(coredump.id) }
                })}
              >
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {new Date(coredump.uploadedAt).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground font-mono">
                  {coredump.firmwareVersion}
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {formatFileSize(coredump.size)}
                </td>
                <td className="px-4 py-3 text-sm text-muted-foreground">
                  {coredump.parseStatus}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <a
                      href={`/api/devices/${deviceId}/coredumps/${coredump.id}/download`}
                      download
                      onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center justify-center rounded-md text-sm font-medium h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-secondary"
                      data-testid="coredumps.table.row.download"
                      title="Download core dump"
                    >
                      <Download className="h-4 w-4" />
                    </a>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDelete(coredump.id, coredump.filename)
                      }}
                      data-testid="coredumps.table.row.delete"
                      title="Delete core dump"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        {...confirmProps}
        contentProps={{ 'data-testid': 'coredumps.delete.confirm-dialog' }}
      />
    </div>
  )
}
