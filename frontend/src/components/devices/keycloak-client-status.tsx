import { useState, useEffect, useCallback, useRef } from 'react'
import { ExternalLink, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useDeviceKeycloakStatus, useSyncDeviceKeycloak } from '@/hooks/use-devices'

interface KeycloakClientStatusProps {
  deviceId: number
}

// Custom hook to manage blinking animation that continues for minimum 2 blinks
function useBlinkingSync(syncMutation: ReturnType<typeof useSyncDeviceKeycloak>, deviceId: number) {
  const [blinkPhase, setBlinkPhase] = useState<number | null>(null) // null = not blinking, number = current phase
  const syncCompletedRef = useRef(false)

  const isBlinking = blinkPhase !== null

  // Handle blinking animation
  useEffect(() => {
    if (blinkPhase === null) return

    const timeout = setTimeout(() => {
      const nextPhase = blinkPhase + 1
      // Stop after sync completes AND we've done at least 2 full blinks (4 phases)
      if (syncCompletedRef.current && nextPhase >= 4) {
        setBlinkPhase(null)
      } else {
        setBlinkPhase(nextPhase)
      }
    }, 400)

    return () => clearTimeout(timeout)
  }, [blinkPhase])

  const startSync = useCallback(() => {
    setBlinkPhase(0)
    syncCompletedRef.current = false
    syncMutation.mutate(
      { deviceId },
      {
        onSuccess: () => {
          syncCompletedRef.current = true
        },
        onError: () => {
          syncCompletedRef.current = true
        }
      }
    )
  }, [syncMutation, deviceId])

  // Icon is visible on even phases (0, 2, 4...) or when not blinking
  const iconVisible = blinkPhase === null || blinkPhase % 2 === 0

  return { isBlinking, iconVisible, startSync }
}

export function KeycloakClientStatus({ deviceId }: KeycloakClientStatusProps) {
  const { status, isLoading, isError } = useDeviceKeycloakStatus(deviceId)
  const syncKeycloak = useSyncDeviceKeycloak()
  const { isBlinking, iconVisible, startSync } = useBlinkingSync(syncKeycloak, deviceId)

  // Show loading state
  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span>Checking Keycloak status...</span>
      </div>
    )
  }

  // Show error state
  if (isError || !status) {
    return (
      <span className="text-muted-foreground" data-testid="devices.editor.keycloak-status-error">
        Unable to check Keycloak status
      </span>
    )
  }

  // Show status with appropriate action
  if (status.exists) {
    return (
      <div className="flex items-center gap-2">
        <span
          className="font-mono text-green-400"
          data-testid="devices.editor.keycloak-client-id"
        >
          {status.clientId}
        </span>
        {status.consoleUrl && (
          <a
            href={status.consoleUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground"
            title="Open in Keycloak console"
            data-testid="devices.editor.keycloak-console-link"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        )}
        <button
          onClick={startSync}
          disabled={isBlinking}
          className="cursor-pointer text-muted-foreground hover:text-foreground disabled:cursor-not-allowed"
          title="Resync Keycloak client"
          data-testid="devices.editor.keycloak-sync"
        >
          <RefreshCw
            className={`h-4 w-4 transition-opacity ${iconVisible ? 'opacity-100' : 'opacity-0'}`}
          />
        </button>
      </div>
    )
  }

  // Client doesn't exist - show recreate option
  return (
    <div className="flex items-center gap-3">
      <span className="text-amber-400" data-testid="devices.editor.keycloak-status-missing">
        Client not found in Keycloak
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={startSync}
        disabled={isBlinking}
        loading={isBlinking}
        data-testid="devices.editor.keycloak-recreate"
      >
        <RefreshCw className="h-3 w-3 mr-1" />
        Recreate Client
      </Button>
    </div>
  )
}
