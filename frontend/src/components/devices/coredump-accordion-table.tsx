import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import Editor from '@monaco-editor/react'
import { Trash2, Download } from 'lucide-react'
import { Button } from '@/components/primitives/button'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ConfirmDialog } from '@/components/primitives/dialog'
import { useConfirm } from '@/hooks/use-confirm'
import { useCoredumps, useCoredump, useDeleteCoredump, formatFileSize } from '@/hooks/use-coredumps'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'
import { useFormInstrumentation } from '@/hooks/use-form-instrumentation'

interface CoredumpAccordionTableProps {
  deviceId: number
  /** When set (from URL deep-link), the row is auto-expanded on mount */
  expandedCoredumpId?: number
}

/**
 * Core dumps table with inline accordion expansion.
 * Clicking a row toggles expansion (only one row at a time).
 * The expanded panel shows metadata and a read-only Monaco editor for parsed output.
 * URL syncs with the expanded row via navigate({ replace: true }).
 */
export function CoredumpAccordionTable({ deviceId, expandedCoredumpId }: CoredumpAccordionTableProps) {
  const { coredumps, isLoading, isFetching, error } = useCoredumps(deviceId)
  const deleteCoredump = useDeleteCoredump()
  const { confirm, confirmProps } = useConfirm()

  const [expandedId, setExpandedId] = useState<number | null>(expandedCoredumpId ?? null)
  const expandedRowRef = useRef<HTMLTableRowElement>(null)

  // Form instrumentation for the delete mutation lifecycle
  const { trackSubmit, trackSuccess, trackError } = useFormInstrumentation({
    formId: 'CoredumpDelete',
    isOpen: true,
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

  // Auto-scroll to expanded row on deep-link mount
  useEffect(() => {
    if (expandedCoredumpId && expandedRowRef.current) {
      expandedRowRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [expandedCoredumpId, sortedCoredumps])

  // Toggle accordion expansion and sync URL via replaceState
  // (avoids route-level unmount/remount that navigate() would trigger)
  const toggleExpanded = useCallback((coredumpId: number) => {
    const next = expandedId === coredumpId ? null : coredumpId
    setExpandedId(next)
    const path = next
      ? `/devices/${deviceId}/coredumps/${next}`
      : `/devices/${deviceId}/coredumps`
    window.history.replaceState(window.history.state, '', path)
  }, [deviceId, expandedId])

  const handleDelete = useCallback(async (coredumpId: number) => {
    const confirmed = await confirm({
      title: 'Delete Core Dump',
      description: `Delete core dump #${coredumpId}? This action cannot be undone.`,
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
            // Collapse if the deleted coredump was expanded
            if (expandedId === coredumpId) {
              setExpandedId(null)
              window.history.replaceState(window.history.state, '', `/devices/${deviceId}/coredumps`)
            }
          },
          onError: (err) => {
            trackError({ error: err instanceof Error ? err.message : 'Unknown error' })
          }
        }
      )
    }
  }, [confirm, deleteCoredump, deviceId, expandedId, trackSubmit, trackSuccess, trackError])

  // Loading skeleton
  if (isLoading) {
    return (
      <div className="p-6" data-testid="coredumps.table">
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
      <div className="p-6" data-testid="coredumps.table">
        <div className="text-destructive" data-testid="coredumps.table.error">
          Failed to load core dumps
        </div>
      </div>
    )
  }

  // Empty state
  if (sortedCoredumps.length === 0) {
    return (
      <div className="p-6" data-testid="coredumps.table">
        <EmptyState
          title="No core dumps recorded for this device"
          data-testid="coredumps.table.empty"
        />
      </div>
    )
  }

  return (
    <div className="p-6" data-testid="coredumps.table">
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
            {sortedCoredumps.map((coredump) => {
              const isExpanded = expandedId === coredump.id
              return (
                <CoredumpRow
                  key={coredump.id}
                  coredump={coredump}
                  deviceId={deviceId}
                  isExpanded={isExpanded}
                  expandedRowRef={isExpanded ? expandedRowRef : undefined}
                  onToggle={() => toggleExpanded(coredump.id)}
                  onDelete={() => handleDelete(coredump.id)}
                />
              )
            })}
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

// --- Row + Expansion Panel ---

interface CoredumpRowProps {
  coredump: ReturnType<typeof useCoredumps>['coredumps'][number]
  deviceId: number
  isExpanded: boolean
  expandedRowRef?: React.Ref<HTMLTableRowElement>
  onToggle: () => void
  onDelete: () => void
}

function CoredumpRow({ coredump, deviceId, isExpanded, expandedRowRef, onToggle, onDelete }: CoredumpRowProps) {
  return (
    <>
      <tr
        className="border-b border-border hover:bg-secondary/50 cursor-pointer"
        data-testid="coredumps.table.row"
        data-coredump-id={coredump.id}
        onClick={onToggle}
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
                onDelete()
              }}
              data-testid="coredumps.table.row.delete"
              title="Delete core dump"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </td>
      </tr>
      {isExpanded && (
        <tr ref={expandedRowRef} data-testid="coredumps.accordion.expanded">
          <td colSpan={5} className="border-b border-border bg-secondary/25 p-0">
            <CoredumpExpansionPanel deviceId={deviceId} coredumpId={coredump.id} />
          </td>
        </tr>
      )}
    </>
  )
}

// --- Expansion Panel (fetches detail + renders metadata/editor) ---

function CoredumpExpansionPanel({ deviceId, coredumpId }: { deviceId: number; coredumpId: number }) {
  const { coredump, isLoading } = useCoredump(deviceId, coredumpId)

  if (isLoading) {
    return (
      <div className="p-6 space-y-3">
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (!coredump) {
    return (
      <div className="p-6 text-sm text-destructive">
        Failed to load core dump details
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      {/* Metadata grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4" data-testid="coredumps.accordion.metadata">
        <MetadataField label="Chip" value={coredump.chip} mono />
        <MetadataField label="Firmware Version" value={coredump.firmwareVersion} mono />
        <MetadataField label="Size" value={formatFileSize(coredump.size)} />
        <MetadataField label="Parse Status" value={coredump.parseStatus} />
        <MetadataField
          label="Uploaded At"
          value={new Date(coredump.uploadedAt).toLocaleString()}
        />
        <MetadataField
          label="Parsed At"
          value={coredump.parsedAt ? new Date(coredump.parsedAt).toLocaleString() : '\u2014'}
        />
      </div>

      {/* Parsed output */}
      {coredump.parsedOutput ? (
        <div
          className="rounded-md border border-border overflow-hidden"
          style={{ maxHeight: '500px' }}
          data-testid="coredumps.accordion.editor"
        >
          <Editor
            height="400px"
            defaultLanguage="plaintext"
            theme="vs-dark"
            value={coredump.parsedOutput}
            options={{
              readOnly: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              wordWrap: 'on',
              lineNumbers: 'on'
            }}
          />
        </div>
      ) : (
        <div
          className="rounded-md border border-border p-8 text-center text-muted-foreground"
          data-testid="coredumps.accordion.no-output"
        >
          Parsed output not available
        </div>
      )}
    </div>
  )
}

/** Reusable metadata field display */
function MetadataField({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
      <dd className={`mt-1 text-sm text-foreground ${mono ? 'font-mono' : ''}`}>{value}</dd>
    </div>
  )
}
