/* eslint-disable react-refresh/only-export-components */
/**
 * App-wide SSE connection manager.
 * Creates a single EventSource to /api/sse/stream on mount (inside AuthGate),
 * exposes a stable requestId and an addEventListener function for consumers
 * (device logs, rotation dashboard) to register named-event handlers.
 *
 * Emits SseTestEvent instrumentation events for the connection lifecycle
 * so Playwright can wait on deterministic signals.
 */

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from 'react'
import { ulid } from 'ulid'
import { isTestMode } from '@/lib/config/test-mode'
import { emitTestEvent } from '@/lib/test/event-emitter'
import { TestEventKind, type SseTestEvent } from '@/types/test-events'

export type SseConnectionState = 'connecting' | 'open' | 'closed'

export interface SseContextValue {
  /** Client-generated ULID correlation ID for this SSE session */
  requestId: string
  /** Register a handler for a named SSE event; returns an unsubscribe function */
  addEventListener: (event: string, handler: (data: unknown) => void) => () => void
  /** Current EventSource connection state */
  connectionState: SseConnectionState
}

export const SseContext = createContext<SseContextValue | null>(null)

/**
 * Hook to access the SSE context.
 * Must be used within SseProvider (which lives inside AuthGate).
 */
export function useSseContext(): SseContextValue {
  const context = useContext(SseContext)
  if (!context) {
    throw new Error('useSseContext must be used within SseProvider')
  }
  return context
}

interface SseProviderProps {
  children: ReactNode
}

/**
 * Emit an SseTestEvent (gated behind isTestMode).
 */
function emitSseEvent(
  streamId: string,
  phase: SseTestEvent['phase'],
  event: string,
  data?: unknown
): void {
  if (!isTestMode()) return

  const payload: Omit<SseTestEvent, 'timestamp'> = {
    kind: TestEventKind.SSE,
    streamId,
    phase,
    event,
    data,
  }
  emitTestEvent(payload)
}

export function SseProvider({ children }: SseProviderProps) {
  // Stable requestId for the lifetime of this provider instance.
  // Using useState with initializer ensures the value is created once
  // and is accessible during render without ref-during-render lint issues.
  const [requestId] = useState(() => ulid())

  const [connectionState, setConnectionState] = useState<SseConnectionState>('connecting')

  // Internal listener registry: Map<eventName, Set<handler>>
  const listenersRef = useRef(new Map<string, Set<(data: unknown) => void>>())

  // addEventListener returns an unsubscribe function.
  // We also attach/detach EventSource listeners dynamically as events are registered.
  const eventSourceRef = useRef<EventSource | null>(null)
  // Track which event names have been attached to the EventSource
  const attachedEventsRef = useRef(new Set<string>())

  // Keep requestId available to callbacks via a ref (stable across renders)
  const requestIdRef = useRef(requestId)

  /**
   * Attach a named-event listener on the EventSource for a given event type.
   * Only attaches once per event name (multiple consumers share via the registry).
   */
  const ensureEventSourceListener = useCallback((eventName: string) => {
    const es = eventSourceRef.current
    if (!es || attachedEventsRef.current.has(eventName)) return

    attachedEventsRef.current.add(eventName)

    es.addEventListener(eventName, (e: MessageEvent) => {
      let parsed: unknown
      try {
        parsed = JSON.parse(e.data)
      } catch {
        parsed = e.data
      }

      // Emit instrumentation for every named message
      emitSseEvent(requestIdRef.current, 'message', eventName, parsed)

      // Dispatch to all registered handlers
      const handlers = listenersRef.current.get(eventName)
      if (handlers) {
        for (const handler of handlers) {
          handler(parsed)
        }
      }
    })
  }, [])

  const addEventListener = useCallback(
    (event: string, handler: (data: unknown) => void): (() => void) => {
      const map = listenersRef.current
      if (!map.has(event)) {
        map.set(event, new Set())
      }
      map.get(event)!.add(handler)

      // Ensure the EventSource has a listener for this event type
      ensureEventSourceListener(event)

      // Return unsubscribe
      return () => {
        const handlers = map.get(event)
        if (handlers) {
          handlers.delete(handler)
          if (handlers.size === 0) {
            map.delete(event)
          }
        }
      }
    },
    [ensureEventSourceListener]
  )

  // Create and manage the EventSource connection
  useEffect(() => {
    const id = requestIdRef.current
    const url = `/api/sse/stream?request_id=${encodeURIComponent(id)}`

    // connectionState starts as 'connecting' via the initial useState value.
    // Subsequent transitions happen in callbacks (onopen, onerror, cleanup),
    // which are not synchronous within the effect body.

    const es = new EventSource(url)
    eventSourceRef.current = es

    // Re-attach any previously registered event listeners (e.g. from consumers
    // that registered before the EventSource was created).
    // Copy to local to avoid stale-ref-in-cleanup warnings.
    const attached = attachedEventsRef.current
    attached.clear()
    for (const eventName of listenersRef.current.keys()) {
      ensureEventSourceListener(eventName)
    }

    es.onopen = () => {
      setConnectionState('open')
      emitSseEvent(id, 'open', 'connection')
    }

    es.onerror = () => {
      emitSseEvent(id, 'error', 'connection')

      if (es.readyState === EventSource.CLOSED) {
        setConnectionState('closed')
        emitSseEvent(id, 'close', 'connection')
      }
      // Otherwise EventSource is in CONNECTING state and will auto-reconnect
    }

    return () => {
      es.close()
      eventSourceRef.current = null
      attached.clear()
      setConnectionState('closed')
      emitSseEvent(id, 'close', 'connection')
    }
  }, [ensureEventSourceListener])

  const contextValue: SseContextValue = {
    requestId,
    addEventListener,
    connectionState,
  }

  return (
    <SseContext.Provider value={contextValue}>
      {children}
    </SseContext.Provider>
  )
}
