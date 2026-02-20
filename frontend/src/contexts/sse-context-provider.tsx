import { useState, useEffect, useCallback, useRef } from 'react';
import type { ReactNode } from 'react';
import { isTestMode } from '@/lib/config/test-mode';
import { emitTestEvent } from '@/lib/test/event-emitter';
import type { SseTestEvent } from '@/lib/test/test-events';
import { SseContext } from './sse-context-base';
import type { SseContextValue } from './sse-context-base';
// Import to ensure test bridge registration (even though module is not used in production)
import '@/lib/config/sse-request-id';

interface SseContextProviderProps {
  children: ReactNode;
}

// Worker message types
type WorkerMessage =
  | { type: 'connected'; requestId: string; __testEvent?: SseTestEventMetadata }
  | { type: 'event'; event: string; data: unknown; __testEvent?: SseTestEventMetadata }
  | { type: 'disconnected'; reason?: string; __testEvent?: SseTestEventMetadata }
  | { type: 'error'; error: string; __testEvent?: SseTestEventMetadata };

interface SseTestEventMetadata {
  kind: 'sse';
  streamId: string;
  phase: 'open' | 'message' | 'error' | 'close';
  event: string;
  data?: unknown;
}

/**
 * Determine if SharedWorker should be used based on environment
 */
function shouldUseSharedWorker(): boolean {
  // Always use direct connection in development mode
  if (import.meta.env.DEV) {
    return false;
  }

  // In test mode, only use SharedWorker if explicitly enabled via URL parameter
  if (isTestMode()) {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return params.has('__sharedWorker');
    }
    return false;
  }

  // Check if SharedWorker is supported (graceful fallback for iOS Safari)
  if (typeof SharedWorker === 'undefined') {
    return false;
  }

  // Production mode with SharedWorker support
  return true;
}

/**
 * SSE context provider that manages a unified SSE connection.
 *
 * Exposes a generic addEventListener interface. Consumer hooks subscribe to
 * named SSE events and handle their own DTO parsing.
 *
 * Uses SharedWorker in production for cross-tab connection sharing, falls back to
 * direct EventSource in dev/test/iOS environments.
 */
export function SseContextProvider({ children }: SseContextProviderProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [requestId, setRequestId] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const sharedWorkerRef = useRef<SharedWorker | null>(null);
  const useSharedWorker = useRef<boolean>(shouldUseSharedWorker());

  // Internal listener registry: Map<eventName, Set<handler>>
  const listenersRef = useRef(new Map<string, Set<(data: unknown) => void>>());

  // Track which event names have been attached to the EventSource (direct mode)
  const attachedEventsRef = useRef(new Set<string>());

  // Track which event names have been subscribed on the SharedWorker
  const workerSubscribedEventsRef = useRef(new Set<string>());

  /**
   * Dispatch an event to all registered handlers for a given event name
   */
  const dispatchEvent = useCallback((eventName: string, data: unknown) => {
    const handlers = listenersRef.current.get(eventName);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(data);
        } catch (error) {
          console.error(`Error in SSE event handler for '${eventName}':`, error);
        }
      }
    }
  }, []);

  /**
   * Attach a named-event listener on the direct EventSource.
   * Only attaches once per event name (multiple consumers share via the registry).
   */
  const ensureDirectEventSourceListener = useCallback((eventName: string) => {
    const es = eventSourceRef.current;
    if (!es || attachedEventsRef.current.has(eventName)) return;

    attachedEventsRef.current.add(eventName);

    es.addEventListener(eventName, (e: MessageEvent) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(e.data);
      } catch {
        parsed = e.data;
      }

      if (isTestMode()) {
        emitTestEvent({
          kind: 'sse',
          streamId: eventName,
          phase: 'message',
          event: eventName,
          data: parsed,
        });
      }

      dispatchEvent(eventName, parsed);
    });
  }, [dispatchEvent]);

  /**
   * Tell the SharedWorker to subscribe to a named SSE event.
   * Only sends the subscribe command once per event name.
   */
  const ensureWorkerSubscription = useCallback((eventName: string) => {
    const worker = sharedWorkerRef.current;
    if (!worker || workerSubscribedEventsRef.current.has(eventName)) return;

    workerSubscribedEventsRef.current.add(eventName);
    worker.port.postMessage({ type: 'subscribe', event: eventName });
  }, []);

  /**
   * Register a handler for a named SSE event.
   * Returns an unsubscribe function.
   */
  const addEventListener = useCallback(
    (event: string, handler: (data: unknown) => void): (() => void) => {
      const map = listenersRef.current;
      if (!map.has(event)) {
        map.set(event, new Set());
      }
      map.get(event)!.add(handler);

      // Ensure the underlying transport is listening for this event
      if (useSharedWorker.current) {
        ensureWorkerSubscription(event);
      } else {
        ensureDirectEventSourceListener(event);
      }

      return () => {
        const handlers = map.get(event);
        if (handlers) {
          handlers.delete(handler);
          if (handlers.size === 0) {
            map.delete(event);
          }
        }
      };
    },
    [ensureDirectEventSourceListener, ensureWorkerSubscription]
  );

  /**
   * Handle worker messages and dispatch to listeners
   */
  const handleWorkerMessage = useCallback((message: WorkerMessage) => {
    // Forward test events if present
    if (message.__testEvent && isTestMode()) {
      emitTestEvent(message.__testEvent);
    }

    switch (message.type) {
      case 'connected':
        setIsConnected(true);
        setRequestId(message.requestId);
        break;

      case 'event':
        dispatchEvent(message.event, message.data);
        break;

      case 'error':
        console.error('SSE connection error:', message.error);
        setIsConnected(false);
        break;

      case 'disconnected':
        console.debug('SSE disconnected:', message.reason);
        setIsConnected(false);
        break;

      default:
        console.warn('Unknown worker message:', message);
    }
  }, [dispatchEvent]);

  /**
   * Create SharedWorker connection
   */
  const createSharedWorkerConnection = useCallback(() => {
    try {
      console.debug('SSE context: Using SharedWorker for unified SSE connection');

      const worker = new SharedWorker(
        new URL('../workers/sse-worker.ts', import.meta.url),
        { type: 'module' }
      );

      sharedWorkerRef.current = worker;

      worker.port.onmessage = (event: MessageEvent<WorkerMessage>) => {
        handleWorkerMessage(event.data);
      };

      worker.port.start();
      worker.port.postMessage({
        type: 'connect',
        isTestMode: isTestMode(),
      });

      // Subscribe the worker to any events that were registered before the worker was created
      workerSubscribedEventsRef.current.clear();
      for (const eventName of listenersRef.current.keys()) {
        ensureWorkerSubscription(eventName);
      }
    } catch (error) {
      console.error('Failed to create SharedWorker, falling back to direct connection:', error);
      useSharedWorker.current = false;
      setIsConnected(false);
    }
  }, [handleWorkerMessage, ensureWorkerSubscription]);

  /**
   * Create direct EventSource connection
   */
  const createDirectConnection = useCallback(() => {
    const tabRequestId = Math.random().toString(36).substring(2, 15) +
                         Math.random().toString(36).substring(2, 15);

    const params = new URLSearchParams({ request_id: tabRequestId });
    const url = `/api/sse/stream?${params}`;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    // Re-attach listeners for any events registered before the EventSource was created
    attachedEventsRef.current.clear();
    for (const eventName of listenersRef.current.keys()) {
      ensureDirectEventSourceListener(eventName);
    }

    eventSource.onopen = () => {
      setIsConnected(true);
      setRequestId(tabRequestId);

      if (isTestMode()) {
        const payload: Omit<SseTestEvent, 'timestamp'> = {
          kind: 'sse',
          streamId: 'connection',
          phase: 'open',
          event: 'connected',
          data: { requestId: tabRequestId },
        };
        emitTestEvent(payload);
      }
    };

    eventSource.addEventListener('connection_close', (event) => {
      try {
        const data = JSON.parse(event.data);
        console.debug('Connection closed by backend:', data.reason);
      } catch {
        // Ignore parse errors
      }
      setIsConnected(false);
    });

    eventSource.onerror = (event) => {
      if (isTestMode()) {
        console.debug('EventSource error (test mode):', event);
      } else {
        console.error('EventSource error:', event);
      }
      setIsConnected(false);
    };
  }, [ensureDirectEventSourceListener]);

  /**
   * Disconnect from SSE
   */
  const disconnect = useCallback(() => {
    if (sharedWorkerRef.current) {
      try {
        sharedWorkerRef.current.port.postMessage({ type: 'disconnect' });
        sharedWorkerRef.current.port.close();
      } catch (error) {
        console.error('Failed to disconnect SharedWorker:', error);
      }
      sharedWorkerRef.current = null;
      workerSubscribedEventsRef.current.clear();
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      attachedEventsRef.current.clear();
    }

    setIsConnected(false);
  }, []);

  /**
   * Reconnect SSE (for focus-based reconnection)
   */
  const reconnect = useCallback(() => {
    if (isConnected) {
      return;
    }

    if (useSharedWorker.current) {
      if (!sharedWorkerRef.current) {
        createSharedWorkerConnection();
      }
      return;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      attachedEventsRef.current.clear();
    }
    createDirectConnection();
  }, [isConnected, createSharedWorkerConnection, createDirectConnection]);

  // Establish connection on mount
  useEffect(() => {
    const hasSharedWorkerParam = typeof window !== 'undefined' &&
      new URLSearchParams(window.location.search).has('__sharedWorker');
    const shouldAutoConnect = !isTestMode() || hasSharedWorkerParam;
    if (!shouldAutoConnect) {
      return;
    }

    if (useSharedWorker.current) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional SSE connection initiation
      createSharedWorkerConnection();
    } else {
      createDirectConnection();
    }

    return () => {
      disconnect();
    };
  }, [createSharedWorkerConnection, createDirectConnection, disconnect]);

  const contextValue: SseContextValue = {
    isConnected,
    requestId,
    addEventListener,
    reconnect,
  };

  return (
    <SseContext.Provider value={contextValue}>
      {children}
    </SseContext.Provider>
  );
}
