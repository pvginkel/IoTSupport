# SSE Redesign - Frontend Changes

## Overview

The backend SSE system has been redesigned to use a single unified endpoint that broadcasts all events to all connected clients. The frontend must be updated to:

1. Connect to the new unified endpoint
2. Filter events client-side by `task_id` or event type
3. Handle the fact that task completion no longer closes the connection

## Breaking Changes

### 1. TaskStartResponse No Longer Includes stream_url

**Old behavior:**
```typescript
interface TaskStartResponse {
  task_id: string;
  stream_url: string;  // No longer provided
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
}
```

**New behavior:**
```typescript
interface TaskStartResponse {
  task_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
}
```

The frontend should use the shared SSE connection (established at app startup) to receive task events, filtering by `task_id`. There is no need to open a new connection per task.

### 2. SSE Endpoint URL Change

**Old behavior:**
```typescript
// Separate endpoints for different event types
const versionUrl = `/api/sse/utils/version?request_id=${requestId}`;
const taskUrl = `/api/sse/tasks?task_id=${taskId}`;
```

**New behavior:**
```typescript
// Single unified endpoint for all events
const sseUrl = `/api/sse/stream?request_id=${requestId}`;
```

### 3. Event Broadcast Model

**Old behavior:**
- Each connection received only events for its specific task or request
- Task completion closed the connection automatically

**New behavior:**
- All connections receive ALL events (version updates, task progress, etc.)
- Frontend MUST filter events by `task_id` or event type
- Connections remain open even after task completion
- Frontend should close connections when no longer needed

## Required Frontend Changes

### 1. Update SSE Connection Establishment

Replace per-service connections with a single unified connection:

```typescript
// OLD: Separate connection per service
function connectToVersionStream(requestId: string) {
  const eventSource = new EventSource(`/api/sse/utils/version?request_id=${requestId}`);
  // ...
}

function connectToTaskStream(taskId: string) {
  const eventSource = new EventSource(`/api/sse/tasks?task_id=${taskId}`);
  // ...
}

// NEW: Single unified connection
function connectToSSE(requestId: string) {
  const eventSource = new EventSource(`/api/sse/stream?request_id=${requestId}`);

  // Listen for version events
  eventSource.addEventListener('version', (event) => {
    const data = JSON.parse(event.data);
    handleVersionUpdate(data);
  });

  // Listen for task events
  eventSource.addEventListener('task_event', (event) => {
    const data = JSON.parse(event.data);
    // IMPORTANT: Filter by task_id
    if (data.task_id === currentTaskId) {
      handleTaskEvent(data);
    }
  });

  return eventSource;
}
```

### 2. Implement Client-Side Event Filtering

All task events now include a `task_id` field for client-side filtering:

```typescript
interface TaskEvent {
  event_type: 'task_started' | 'progress_update' | 'task_completed' | 'task_failed';
  task_id: string;  // Use this for filtering!
  timestamp: string;
  data: any;
}

// Example filter implementation
eventSource.addEventListener('task_event', (event) => {
  const taskEvent: TaskEvent = JSON.parse(event.data);

  // Only process events for tasks you care about
  if (activeTaskIds.has(taskEvent.task_id)) {
    handleTaskEvent(taskEvent);
  }
});
```

### 3. Handle Connection Lifecycle

Connections no longer close automatically on task completion:

```typescript
// OLD: Connection closed automatically
eventSource.addEventListener('task_event', (event) => {
  const data = JSON.parse(event.data);
  if (data.event_type === 'task_completed') {
    // Connection automatically closes - no cleanup needed
    handleTaskComplete(data);
  }
});

// NEW: Close connection manually when done
eventSource.addEventListener('task_event', (event) => {
  const data = JSON.parse(event.data);

  if (data.event_type === 'task_completed' && data.task_id === currentTaskId) {
    handleTaskComplete(data);

    // Clean up: close connection if no other tasks are active
    if (noOtherActiveTasksRemaining()) {
      eventSource.close();
    }
  }
});
```

### 4. Shared Connection Pattern (Recommended)

To avoid HTTP/1.1 connection limits, use a shared EventSource connection:

```typescript
class SSEManager {
  private eventSource: EventSource | null = null;
  private requestId: string;
  private listeners: Map<string, Set<(event: any) => void>> = new Map();

  constructor(requestId: string) {
    this.requestId = requestId;
  }

  connect() {
    if (this.eventSource) return; // Already connected

    this.eventSource = new EventSource(`/api/sse/stream?request_id=${this.requestId}`);

    // Forward version events
    this.eventSource.addEventListener('version', (event) => {
      const data = JSON.parse(event.data);
      this.notifyListeners('version', data);
    });

    // Forward task events (with filtering)
    this.eventSource.addEventListener('task_event', (event) => {
      const data = JSON.parse(event.data);
      this.notifyListeners(`task:${data.task_id}`, data);
    });
  }

  subscribeToTask(taskId: string, callback: (event: any) => void) {
    const key = `task:${taskId}`;
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key)!.add(callback);
  }

  unsubscribeFromTask(taskId: string, callback: (event: any) => void) {
    const key = `task:${taskId}`;
    this.listeners.get(key)?.delete(callback);

    // Clean up empty listener sets
    if (this.listeners.get(key)?.size === 0) {
      this.listeners.delete(key);
    }

    // Close connection if no more listeners
    if (this.listeners.size === 0 && this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  private notifyListeners(key: string, data: any) {
    this.listeners.get(key)?.forEach(callback => callback(data));
  }
}

// Usage
const sseManager = new SSEManager(generateRequestId());
sseManager.connect();

// Subscribe to task events
const handleTaskProgress = (event: any) => {
  console.log('Task progress:', event);
};

sseManager.subscribeToTask('task-123', handleTaskProgress);

// Later: unsubscribe when done
sseManager.unsubscribeFromTask('task-123', handleTaskProgress);
```

### 5. SharedWorker Pattern (Advanced)

For apps with multiple tabs, use SharedWorker to share a single SSE connection:

```typescript
// shared-sse-worker.ts
const connections = new Map<string, EventSource>();

self.onconnect = (event) => {
  const port = event.ports[0];

  port.onmessage = (msg) => {
    const { action, requestId, taskId } = msg.data;

    if (action === 'connect') {
      if (!connections.has(requestId)) {
        const es = new EventSource(`/api/sse/stream?request_id=${requestId}`);

        es.addEventListener('task_event', (event) => {
          const data = JSON.parse(event.data);
          // Broadcast to all tabs
          port.postMessage({ type: 'task_event', data });
        });

        connections.set(requestId, es);
      }
    }

    if (action === 'disconnect') {
      const es = connections.get(requestId);
      es?.close();
      connections.delete(requestId);
    }
  };
};
```

## Migration Checklist

- [ ] Update SSE connection URL to `/api/sse/stream?request_id=X`
- [ ] Implement client-side filtering by `task_id` for task events
- [ ] Remove assumption that task completion closes connection
- [ ] Add explicit `eventSource.close()` calls when done with connection
- [ ] Update tests to expect events from unified endpoint
- [ ] Consider implementing SharedWorker for multi-tab support
- [ ] Update any documentation referencing old endpoint URLs

## Event Schema Reference

### Version Event
```json
{
  "version": "1.2.3",
  "changelog": "Optional changelog text"
}
```
Event name: `version`

### Task Event
```json
{
  "event_type": "task_started" | "progress_update" | "task_completed" | "task_failed",
  "task_id": "abc-123",
  "timestamp": "2025-01-15T10:30:00Z",
  "data": {
    // Event-specific data
  }
}
```
Event name: `task_event`

**Critical:** Always filter task events by `task_id` since all events are broadcast to all connections.

## Testing Considerations

1. **Test event filtering:** Verify that task events for other tasks are ignored
2. **Test connection reuse:** Ensure a single connection handles both version and task events
3. **Test manual close:** Verify connections close properly when explicitly closed
4. **Test reconnection:** Handle connection drops and reconnection logic
5. **Test multi-task:** Ensure multiple concurrent tasks work with shared connection

## Rollout Strategy

Since this is a breaking change with no backward compatibility:

1. Deploy backend and frontend changes **atomically** in the same release
2. Expect brief SSE disconnections during deployment
3. Clients will reconnect automatically to the new endpoint
4. No migration of in-flight events (acceptable per design)

## Questions or Issues

Contact the backend team if you encounter issues with:
- Event filtering not working as expected
- Connection close behavior
- Missing events or event ordering
- Performance with many concurrent tasks
