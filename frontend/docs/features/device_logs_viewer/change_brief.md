# Device Logs Viewer

## Summary

Add a real-time log viewer to the device edit screen that displays logging information from Elasticsearch for the device being edited.

## Functional Requirements

### UI Layout
- Display a terminal-style log viewer box below the device editor form (below the JSON configuration section)
- Fixed height of approximately 30 lines
- Dark terminal styling: `bg-gray-900` with `font-mono text-gray-200`
- Only visible in edit mode (not new/duplicate modes)

### Controls
- Checkbox above the log box, aligned to the right, labeled to toggle live updates
- Checkbox is checked (live updates enabled) by default

### Log Display
- Show log messages without timestamps (for now)
- Auto-scroll to bottom when new messages arrive, but only if the scrollbar is already at the bottom
- If user has scrolled up, do not auto-scroll (preserve their reading position)
- Hide the entire log viewer section when the device has no `entity_id` configured or when there are no logs

### Polling Behavior
- Start fetching logs immediately when entering edit mode (no initial history load)
- Poll every 1 second when live updates checkbox is enabled
- Use cursor-based fetching:
  1. Initial call without `start`/`end` parameters returns the current position (window_start equals window_end)
  2. Subsequent polls set `start` to the previous response's `window_end`
  3. If response indicates `has_more`, immediately fetch again (loop until caught up)
- When live updates checkbox is unchecked, stop polling

### Error Handling
- Silently retry on network errors or API failures (continue polling on next interval)
- No toast notifications or visible error states for polling failures

## API Endpoint

`GET /api/devices/{device_id}/logs`

Query parameters:
- `start` (ISO datetime) - Start of time range
- `end` (ISO datetime) - End of time range
- `query` (string) - Wildcard search (not used in this implementation)

Response:
- `logs[]` - Array of `{ message: string, timestamp: string }`
- `has_more` - Boolean indicating more results exist
- `window_start` - Timestamp of first returned log
- `window_end` - Timestamp of last returned log
