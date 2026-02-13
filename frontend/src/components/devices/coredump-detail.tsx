import { Link } from '@tanstack/react-router'
import Editor from '@monaco-editor/react'
import { ArrowLeft, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { CoredumpDetail as CoredumpDetailType } from '@/hooks/use-coredumps'
import { formatFileSize } from '@/lib/utils/format'

interface CoredumpDetailProps {
  coredump: CoredumpDetailType
  /** String device ID for route params */
  deviceId: string
}

/**
 * Core dump detail page component.
 * Displays metadata, a download link, and a read-only Monaco editor for parsed output.
 */
export function CoredumpDetail({ coredump, deviceId }: CoredumpDetailProps) {
  return (
    <div className="flex h-full flex-col" data-testid="coredumps.detail">
      {/* Header with back link and title */}
      <div className="border-b border-border bg-background p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/devices/$deviceId" params={{ deviceId }}>
              <Button variant="outline" size="sm" data-testid="coredumps.detail.back">
                <ArrowLeft className="h-4 w-4 mr-1" />
                Back to Device
              </Button>
            </Link>
            <h1 className="text-2xl font-bold text-foreground">
              Core Dump: <span className="font-mono">{coredump.filename}</span>
            </h1>
          </div>
          <a
            href={`/api/devices/${coredump.deviceId}/coredumps/${coredump.id}/download`}
            download
            data-testid="coredumps.detail.download"
          >
            <Button variant="outline">
              <Download className="h-4 w-4 mr-2" />
              Download
            </Button>
          </a>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Metadata section */}
          <div data-testid="coredumps.detail.metadata">
            <h2 className="text-lg font-semibold text-foreground mb-4">Details</h2>
            <div className="grid grid-cols-2 gap-4">
              <MetadataField label="Filename" value={coredump.filename} mono />
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
                value={coredump.parsedAt ? new Date(coredump.parsedAt).toLocaleString() : '—'}
              />
            </div>
          </div>

          {/* Parsed output section */}
          <div>
            <h2 className="text-lg font-semibold text-foreground mb-4">Parsed Output</h2>
            {coredump.parsedOutput ? (
              <div
                className="rounded-md border border-border overflow-hidden"
                style={{ height: '500px' }}
                data-testid="coredumps.detail.editor"
              >
                <Editor
                  height="100%"
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
                data-testid="coredumps.detail.no-output"
              >
                Parsed output not available
              </div>
            )}
          </div>
        </div>
      </div>
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
