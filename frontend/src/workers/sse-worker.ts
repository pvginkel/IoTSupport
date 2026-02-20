/**
 * SharedWorker for multiplexing a unified SSE connection across browser tabs.
 *
 * Maintains a single EventSource connection to the SSE endpoint and forwards
 * named events to all connected tabs via MessagePort. Tabs dynamically subscribe
 * to event names they care about; the worker attaches EventSource listeners on demand.
 *
 * When the last tab disconnects, the worker closes the SSE connection.
 */

// Type definitions for worker messages

interface TestEventMetadata {
  kind: 'sse';
  streamId: string;
  phase: 'open' | 'message' | 'error' | 'close';
  event: string;
  data?: unknown;
}

type WorkerMessage =
  | { type: 'connected'; requestId: string; __testEvent?: TestEventMetadata }
  | { type: 'event'; event: string; data: unknown; __testEvent?: TestEventMetadata }
  | { type: 'disconnected'; reason?: string; __testEvent?: TestEventMetadata }
  | { type: 'error'; error: string; __testEvent?: TestEventMetadata };

type TabCommand =
  | { type: 'connect'; isTestMode?: boolean }
  | { type: 'disconnect' }
  | { type: 'subscribe'; event: string };

// Token generation utility (inline version of makeUniqueToken)
const TOKEN_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789';
function makeUniqueToken(length = 32): string {
  let token = '';
  for (let i = 0; i < length; i++) {
    token += TOKEN_CHARS.charAt(Math.floor(Math.random() * TOKEN_CHARS.length));
  }
  return token;
}

// Worker state
const ports = new Set<MessagePort>();
const portTestModeMap = new WeakMap<MessagePort, boolean>();
let eventSource: EventSource | null = null;
let currentRequestId: string | null = null;
let retryCount = 0;
let retryTimeout: ReturnType<typeof setTimeout> | null = null;
const maxRetryDelay = 60000; // 60 seconds

// Track which event names have been attached to the EventSource
const subscribedEvents = new Set<string>();

/**
 * Broadcast a message to all connected tabs
 */
function broadcast(message: WorkerMessage): void {
  ports.forEach(port => {
    try {
      port.postMessage(message);
    } catch (error) {
      console.error('SSE worker: Failed to post message to port:', error);
      ports.delete(port);
    }
  });
}

/**
 * Create test event metadata for instrumentation
 */
function createTestEvent(
  streamId: string,
  phase: 'open' | 'message' | 'error' | 'close',
  event: string,
  data?: unknown
): TestEventMetadata {
  return {
    kind: 'sse',
    streamId,
    phase,
    event,
    data,
  };
}

/**
 * Check if any connected port is in test mode
 */
function hasTestModePorts(): boolean {
  return Array.from(ports).some(port => portTestModeMap.get(port));
}

/**
 * Close the SSE connection and clean up resources
 */
function closeConnection(): void {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  if (retryTimeout) {
    clearTimeout(retryTimeout);
    retryTimeout = null;
  }
  currentRequestId = null;
  retryCount = 0;
  subscribedEvents.clear();
}

/**
 * Schedule reconnection with exponential backoff
 */
function scheduleReconnect(): void {
  if (ports.size === 0) {
    closeConnection();
    return;
  }

  if (retryTimeout) {
    clearTimeout(retryTimeout);
    retryTimeout = null;
  }

  retryCount++;
  const delay = Math.min(1000 * Math.pow(2, retryCount - 1), maxRetryDelay);

  console.debug(`SSE worker: Scheduling reconnection in ${delay}ms (attempt ${retryCount})`);

  retryTimeout = setTimeout(() => {
    if (ports.size > 0) {
      createEventSource();
    }
  }, delay);
}

/**
 * Attach a named-event listener on the EventSource.
 * Parses JSON data and broadcasts to all tabs.
 */
function subscribeToEvent(eventName: string): void {
  if (!eventSource || subscribedEvents.has(eventName)) return;

  subscribedEvents.add(eventName);

  eventSource.addEventListener(eventName, (e: MessageEvent) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(e.data);
    } catch {
      parsed = e.data;
    }

    const message: WorkerMessage = {
      type: 'event',
      event: eventName,
      data: parsed,
    };

    if (hasTestModePorts()) {
      message.__testEvent = createTestEvent(eventName, 'message', eventName, parsed);
    }

    broadcast(message);
  });
}

/**
 * Create EventSource connection to unified SSE endpoint
 */
function createEventSource(): void {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  if (!currentRequestId) {
    currentRequestId = makeUniqueToken(32);
  }

  const params = new URLSearchParams({ request_id: currentRequestId });
  const url = `/api/sse/stream?${params.toString()}`;

  console.debug(`SSE worker: Creating EventSource for requestId=${currentRequestId}`);

  // Preserve previously subscribed event names so we can re-attach after reconnection
  const previousEvents = new Set(subscribedEvents);
  subscribedEvents.clear();

  eventSource = new EventSource(url);

  eventSource.onopen = () => {
    console.debug('SSE worker: SSE connection opened');
    retryCount = 0;

    // Re-attach listeners for previously subscribed events
    for (const eventName of previousEvents) {
      subscribeToEvent(eventName);
    }

    const message: WorkerMessage = {
      type: 'connected',
      requestId: currentRequestId!,
    };

    if (hasTestModePorts()) {
      message.__testEvent = createTestEvent('connection', 'open', 'connected', {
        requestId: currentRequestId,
      });
    }

    broadcast(message);
  };

  eventSource.addEventListener('connection_close', (event) => {
    try {
      const data = JSON.parse(event.data);
      console.debug('SSE worker: Connection closed by backend:', data.reason);
    } catch {
      // Ignore parse errors for connection_close
    }

    closeConnection();
  });

  eventSource.onerror = (event) => {
    console.error('SSE worker: EventSource error:', event);

    const errorMessage: WorkerMessage = {
      type: 'error',
      error: 'SSE connection error',
    };

    if (hasTestModePorts()) {
      errorMessage.__testEvent = createTestEvent('connection', 'error', 'error', {
        error: 'SSE connection error',
      });
    }

    broadcast(errorMessage);

    scheduleReconnect();
  };
}

/**
 * Handle tab connection
 */
function handleConnect(port: MessagePort, isTestMode = false): void {
  console.debug(`SSE worker: Tab connected (${ports.size + 1} active ports)`);

  if (isTestMode) {
    portTestModeMap.set(port, true);
  }

  ports.add(port);

  if (!eventSource) {
    createEventSource();
  } else if (eventSource.readyState === EventSource.OPEN) {
    // SSE already connected - send connected message to new tab
    const connectedMessage: WorkerMessage = {
      type: 'connected',
      requestId: currentRequestId!,
    };

    if (isTestMode) {
      connectedMessage.__testEvent = createTestEvent('connection', 'open', 'connected', {
        requestId: currentRequestId,
      });
    }

    try {
      port.postMessage(connectedMessage);
    } catch (error) {
      console.error('SSE worker: Failed to send connected message to new tab:', error);
      ports.delete(port);
    }
  }
}

/**
 * Handle tab disconnection
 */
function handleDisconnect(port: MessagePort): void {
  ports.delete(port);
  portTestModeMap.delete(port);

  console.debug(`SSE worker: Tab disconnected (${ports.size} active ports)`);

  if (ports.size === 0) {
    console.debug('SSE worker: Last tab disconnected, closing SSE connection');
    closeConnection();
  }
}

/**
 * Handle event subscription from a tab
 */
function handleSubscribe(eventName: string): void {
  subscribeToEvent(eventName);
}

/**
 * SharedWorker onconnect handler
 */
self.addEventListener('connect', (event) => {
  const messageEvent = event as MessageEvent;
  const port = messageEvent.ports[0];

  port.onmessage = (messageEvent: MessageEvent<TabCommand>) => {
    const command = messageEvent.data;

    switch (command.type) {
      case 'connect':
        handleConnect(port, command.isTestMode);
        break;

      case 'disconnect':
        handleDisconnect(port);
        break;

      case 'subscribe':
        handleSubscribe(command.event);
        break;

      default:
        console.warn('SSE worker: Unknown command:', command);
    }
  };

  port.addEventListener('messageerror', () => {
    console.debug('SSE worker: Port message error, removing port');
    handleDisconnect(port);
  });

  port.start();
});

console.debug('SSE worker: Initialized');
