# Frontend Instructions: AI Testing Mode for Playwright

## Overview

The backend AI endpoints (`/ai-parts/analyze` and `/ai-parts/cleanup`) now support a **testing mode** that allows Playwright end-to-end tests to exercise the full SSE flow without mocking or calling real AI services.

## How It Works

### Testing Mode Behavior

When `FLASK_ENV=testing`, the AI endpoints:
1. **Skip all validation** (input requirements, part existence checks, content type validation)
2. **Generate a random UUID** as the task ID
3. **Return immediately** with a `TaskStartResponse` (HTTP 201)
4. **Do nothing else** (no task registration, no execution, no AI calls)

The returned task ID is a valid UUID that can be used with the `/api/testing/sse/task-event` endpoint to send controlled SSE events.

### Example Response

```json
POST /api/ai-parts/analyze
Response (201):
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

## Playwright Testing Flow

### 1. Establish SSE Connection

Before calling the AI endpoint, establish an SSE connection to receive events:

```typescript
// Connect to SSE endpoint
const sseConnection = await page.goto('/api/sse/events');
const eventSource = new EventSource('/api/sse/events');

// Set up event listeners
const events: any[] = [];
eventSource.addEventListener('message', (event) => {
  events.push(JSON.parse(event.data));
});
```

### 2. Call the AI Endpoint

Call the AI endpoint to get a task ID:

```typescript
// Call analyze endpoint
const response = await page.request.post('/api/ai-parts/analyze', {
  data: { text: 'Arduino Uno' },
  headers: { 'Content-Type': 'multipart/form-data' }
});

const { task_id } = await response.json();
```

### 3. Send Test Events via Testing Endpoint

Use the `/api/testing/sse/task-event` endpoint to send controlled events to your SSE connection:

```typescript
// Send progress event
await page.request.post('/api/testing/sse/task-event', {
  data: {
    task_id: task_id,
    event_type: 'progress',
    data: {
      message: 'Analyzing part information...',
      percentage: 50
    }
  }
});

// Send completion event
await page.request.post('/api/testing/sse/task-event', {
  data: {
    task_id: task_id,
    event_type: 'completed',
    data: {
      description: 'Arduino Uno R3 Development Board',
      manufacturer_code: 'A000066',
      type: 'Microcontroller Board',
      tags: ['arduino', 'atmega328p', '5v'],
      documents: []
    }
  }
});
```

### 4. Verify UI Updates

Assert that your UI correctly displays the SSE events:

```typescript
// Wait for progress update to appear
await expect(page.locator('[data-testid="progress-message"]'))
  .toHaveText('Analyzing part information...');

// Wait for completion and verify results
await expect(page.locator('[data-testid="part-description"]'))
  .toHaveText('Arduino Uno R3 Development Board');
```

## Testing Endpoint Reference

### POST `/api/testing/sse/task-event`

Sends a task event to all active SSE connections.

**Request Body:**
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "progress",  // or "completed", "error", etc.
  "data": {
    // Event-specific data
  }
}
```

**Response (200):**
```json
{
  "message": "Event sent to 1 connection(s)"
}
```

**Response (400) - No Active Connections:**
```json
{
  "error": "No active SSE connection found for task 550e8400-e29b-41d4-a716-446655440000"
}
```

## Event Types

### Analysis Task Events

- `progress`: Analysis in progress
  ```json
  { "message": "Analyzing...", "percentage": 50 }
  ```

- `completed`: Analysis complete
  ```json
  {
    "description": "Part description",
    "manufacturer_code": "ABC123",
    "type": "Resistor",
    "tags": ["smd", "0603"],
    "documents": []
  }
  ```

- `error`: Analysis failed
  ```json
  { "message": "Failed to analyze part", "code": "AI_ERROR" }
  ```

### Cleanup Task Events

- `progress`: Cleanup in progress
  ```json
  { "message": "Cleaning up part data...", "percentage": 75 }
  ```

- `completed`: Cleanup complete
  ```json
  {
    "changes": {
      "description": "Updated description",
      "tags": ["tag1", "tag2"]
    }
  }
  ```

- `error`: Cleanup failed
  ```json
  { "message": "Failed to cleanup part", "code": "AI_ERROR" }
  ```

## Important Notes

### Testing Mode Requirements

- **Only available when `FLASK_ENV=testing`**
- The `/api/testing/*` endpoints return 404 in production/development
- Validation is **completely bypassed** in testing mode - any payload returns a task ID

### Migration from Mocks

If your tests currently mock AI responses:

1. **Remove mock setup** for AI endpoints
2. **Keep the SSE connection setup** you already have
3. **Add calls to `/api/testing/sse/task-event`** to send controlled events
4. **Keep your existing assertions** - the UI behavior should be identical

### Example: Complete Test

```typescript
test('AI analysis flow displays progress and results', async ({ page }) => {
  // 1. Connect to SSE
  const events: any[] = [];
  await page.route('/api/sse/events', async (route) => {
    // Set up SSE event capture
  });

  // 2. Call AI endpoint
  const response = await page.request.post('/api/ai-parts/analyze', {
    data: { text: 'Test part' }
  });
  const { task_id } = await response.json();

  // 3. Send progress event
  await page.request.post('/api/testing/sse/task-event', {
    data: {
      task_id,
      event_type: 'progress',
      data: { message: 'Analyzing...', percentage: 50 }
    }
  });

  // 4. Verify progress is shown
  await expect(page.locator('[data-testid="ai-progress"]'))
    .toContainText('Analyzing...');

  // 5. Send completion event
  await page.request.post('/api/testing/sse/task-event', {
    data: {
      task_id,
      event_type: 'completed',
      data: {
        description: 'Test Component',
        manufacturer_code: 'TEST123',
        type: 'IC',
        tags: ['test'],
        documents: []
      }
    }
  });

  // 6. Verify results are displayed
  await expect(page.locator('[data-testid="ai-result-description"]'))
    .toHaveText('Test Component');
});
```

## Result Endpoints Removed

The following endpoints have been **removed** as they were unused by the frontend:

- `GET /api/ai-parts/analyze/{task_id}/result`
- `GET /api/ai-parts/cleanup/{task_id}/result`

These endpoints only existed for OpenAPI schema documentation. All result data is delivered via SSE events.

## Configuration Changes

The environment variable `DISABLE_REAL_AI_ANALYSIS` has been renamed to `AI_TESTING_MODE` for clarity. This is an internal backend change that does not affect the frontend API contract.

## Questions?

If you have questions about the testing infrastructure or need additional event types supported, reach out to the backend team.
