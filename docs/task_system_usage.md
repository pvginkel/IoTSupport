# Task System Usage Guide

## Overview

The Electronics Inventory backend provides a transient task management system that allows background jobs to be started via API endpoints and monitored through Server-Sent Events (SSE) streams. This system is designed for operations that take time to complete and benefit from real-time progress updates.

**Important:** All task state is kept in-memory and is intentionally ephemeral. Task state is lost on application restarts, which is expected behavior. Additionally, completed tasks are automatically cleaned up after 10 minutes to prevent memory buildup.

## Core Components

### BaseTask Abstract Class

All background tasks must inherit from `BaseTask` and implement the abstract `execute` method:

```python
from app.services.base_task import BaseTask, ProgressHandle
from pydantic import BaseModel, Field

class MyTaskResult(BaseModel):
    """Result schema for MyTask."""
    result: str = Field(description="Task result status")
    data: str = Field(description="Task output data")

class MyTaskCancelledResult(BaseModel):
    """Result schema for cancelled MyTask."""
    status: str = Field(description="Cancellation status")

class MyTask(BaseTask):
    def execute(self, progress_handle: ProgressHandle, **kwargs) -> BaseModel:
        # Your task implementation
        progress_handle.send_progress("Starting task...", 0.0)
        
        # Do some work
        progress_handle.send_progress("Processing...", 0.5)
        
        # Check for cancellation
        if self.is_cancelled:
            return MyTaskCancelledResult(status="cancelled")
            
        # Complete work
        progress_handle.send_progress("Completed", 1.0)
        
        return MyTaskResult(result="success", data="task output")
```

### Progress Reporting

The `ProgressHandle` interface provides methods to send updates to connected clients:

- `send_progress_text(text: str)` - Send text-only update
- `send_progress_value(value: float)` - Send progress value (0.0 to 1.0)
- `send_progress(text: str, value: float)` - Send both text and value

### Task Events

The system sends these event types via SSE:

1. **task_started** - Task execution began
2. **progress_update** - Progress text or value update
3. **task_completed** - Task finished successfully with result
4. **task_failed** - Task failed with error details

## Creating Background Tasks

### Step 1: Create Your Task Class

```python
# app/services/my_background_task.py
from app.services.base_task import BaseTask, ProgressHandle
from pydantic import BaseModel, Field
import time

class DataProcessingResult(BaseModel):
    """Result schema for successful data processing."""
    processed_records: int = Field(description="Number of records processed")
    file_path: str = Field(description="Path to processed file")
    success: bool = Field(description="Whether processing succeeded")

class DataProcessingCancelledResult(BaseModel):
    """Result schema for cancelled data processing."""
    status: str = Field(description="Cancellation status")

class DataProcessingTask(BaseTask):
    def execute(self, progress_handle: ProgressHandle, **kwargs) -> BaseModel:
        file_path = kwargs.get('file_path')
        batch_size = kwargs.get('batch_size', 100)
        
        progress_handle.send_progress("Loading data...", 0.1)
        
        # Simulate data loading
        time.sleep(1)
        
        if self.is_cancelled:
            return DataProcessingCancelledResult(status="cancelled")
            
        progress_handle.send_progress("Processing records...", 0.5)
        
        # Simulate processing with progress updates
        for i in range(5):
            if self.is_cancelled:
                return DataProcessingCancelledResult(status="cancelled")
                
            time.sleep(0.5)
            progress = 0.5 + (i + 1) * 0.1
            progress_handle.send_progress(f"Processed batch {i+1}/5", progress)
        
        return DataProcessingResult(
            processed_records=500,
            file_path=file_path,
            success=True
        )
```

### Step 2: Create API Endpoint to Start Task

```python
# app/api/data_processing.py
from flask import Blueprint, request, jsonify
from dependency_injector.wiring import Provide, inject

from app.services.container import ServiceContainer
from app.services.task_service import TaskService
from app.services.my_background_task import DataProcessingTask
from app.utils.error_handling import handle_api_errors

data_bp = Blueprint("data", __name__, url_prefix="/api/data")

@data_bp.route("/process", methods=["POST"])
@handle_api_errors
@inject
def start_processing(task_service=Provide[ServiceContainer.task_service]):
    """Start background data processing task."""
    data = request.get_json() or {}
    file_path = data.get('file_path')
    batch_size = data.get('batch_size', 100)
    
    if not file_path:
        return jsonify({"error": "file_path is required"}), 400
    
    # Create and start task
    task = DataProcessingTask()
    task_response = task_service.start_task(
        task,
        file_path=file_path,
        batch_size=batch_size
    )
    
    return jsonify(task_response.model_dump()), 201
```

### Step 3: Register Your API Blueprint

Add your blueprint to `app/api/__init__.py`:

```python
from app.api.data_processing import data_bp  # noqa: E402

api_bp.register_blueprint(data_bp)
```

And wire it in `app/__init__.py`:

```python
container.wire(modules=[..., 'app.api.data_processing'])
```

## Client-Side Usage

### Starting a Task

```javascript
// Start the task
const response = await fetch('/api/data/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_path: '/path/to/file.csv' })
});

const taskInfo = await response.json();
console.log('Task started:', taskInfo.task_id);

// Connect to SSE stream
const eventSource = new EventSource(taskInfo.stream_url);

eventSource.addEventListener('task_event', (event) => {
    const data = JSON.parse(event.data);
    
    switch (data.event_type) {
        case 'task_started':
            console.log('Task started');
            break;
            
        case 'progress_update':
            console.log('Progress:', data.data.text, data.data.value);
            updateProgressBar(data.data.value);
            break;
            
        case 'task_completed':
            console.log('Task completed:', data.data);
            eventSource.close();
            break;
            
        case 'task_failed':
            console.error('Task failed:', data.data.error);
            eventSource.close();
            break;
    }
});

eventSource.addEventListener('error', (event) => {
    console.error('SSE connection error:', event);
});
```

### Task Management

```javascript
// Get task status
const status = await fetch(`/api/tasks/${taskId}/status`);
const statusData = await status.json();

// Cancel a task
await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST' });

// Remove completed task
await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
```

## Best Practices

### Task Design

1. **Keep tasks focused** - Each task should handle one specific operation
2. **Make tasks resumable** - Design tasks to handle partial completion
3. **Implement cancellation** - Always check `self.is_cancelled` in long-running loops
4. **Provide meaningful progress** - Update progress frequently with descriptive text

### Progress Updates

1. **Use descriptive text** - Help users understand what's happening
2. **Update progress values consistently** - Use 0.0 to 1.0 scale
3. **Don't spam updates** - Limit updates to reasonable frequency (every second or major step)

### Error Handling

1. **Return typed results** - Always return a BaseModel schema from execute()
2. **Handle exceptions gracefully** - Let the TaskService catch and report exceptions
3. **Validate inputs** - Check required parameters at the start of execute()

### API Design

1. **Validate input early** - Check required parameters before starting tasks
2. **Return task info immediately** - Don't wait for task completion in API endpoints
3. **Use appropriate HTTP status codes** - 201 for task creation, 404 for not found

## Configuration

The TaskService can be configured with:

- `max_workers` - Maximum concurrent tasks (default: 4)
- `task_timeout` - Task execution timeout in seconds (default: 300)
- `cleanup_interval` - How often to clean up completed tasks in seconds (default: 600)

```python
# In container configuration
task_service = providers.Singleton(
    TaskService, 
    max_workers=8, 
    task_timeout=600,
    cleanup_interval=300  # Clean up every 5 minutes instead of 10
)
```

### Automatic Cleanup

Completed, failed, and cancelled tasks are automatically removed from memory after the `cleanup_interval` (default: 10 minutes) to prevent memory leaks. This cleanup:

- Runs in a background thread
- Only removes tasks that are older than the cleanup interval
- Preserves running tasks regardless of age
- Properly cleans up SSE connections and internal state

## Limitations

1. **In-memory only** - All task state is lost on application restart
2. **No persistence** - Tasks cannot be resumed after server restart  
3. **No distributed execution** - Tasks run on single server instance
4. **Automatic cleanup** - Completed tasks are automatically removed after 10 minutes

## Testing Tasks

### Unit Testing

```python
# tests/test_my_background_task.py
import pytest
from unittest.mock import Mock

from app.services.my_background_task import DataProcessingTask, DataProcessingResult

class TestDataProcessingTask:
    def test_execute_success(self):
        task = DataProcessingTask()
        progress_handle = Mock()
        
        result = task.execute(
            progress_handle,
            file_path="/test/file.csv",
            batch_size=50
        )
        
        assert isinstance(result, DataProcessingResult)
        assert result.success is True
        assert result.processed_records == 500
        assert result.file_path == "/test/file.csv"
        progress_handle.send_progress.assert_called()
```

### Integration Testing

```python
# tests/test_task_integration.py
def test_task_execution_via_service(app, container):
    task_service = container.task_service()
    task = DataProcessingTask()
    
    response = task_service.start_task(
        task,
        file_path="/test/file.csv"
    )
    
    assert response.task_id
    assert "stream" in response.stream_url
    
    # Wait for completion and check events
    events = task_service.get_task_events(response.task_id, timeout=10.0)
    assert any(e.event_type == "task_completed" for e in events)
```

This system provides a robust foundation for background task processing with real-time progress updates. All task state is transient by design, making it suitable for operations that can be safely restarted if needed.