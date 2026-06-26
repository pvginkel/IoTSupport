# Change Brief: Device Logs Backfill & Download

## Summary

Two enhancements to the device log viewer screen:

### 1. Infinite Scroll Backfill (scroll to top)

When the user scrolls to the top of the log viewer, automatically fetch older log entries and prepend them above the current content. This "backfills" the log history as the user scrolls upward.

- Uses infinite-scroll pattern (no explicit button).
- Scroll position must be preserved after prepending — the user stays where they were reading.
- No loading indicator needed.
- The buffer limit is increased from 5,000 to 10,000 entries. Stop loading more history once 10,000 entries are reached.
- The existing backend endpoint `GET /api/devices/{device_id}/logs?end=<ISO>` returns up to 1,000 log lines going backward from the `end` timestamp. Pagination is achieved by setting `end` to the timestamp of the earliest currently-loaded log entry.

### 2. Download Button with Line-Count Dialog

Add a download button (Download icon) in the top-right toolbar area of the log viewer, next to the streaming status indicator.

When clicked, a dialog appears allowing the user to select the number of lines to retrieve: **100, 500, 1,000, 5,000, 10,000**.

Behavior:
- The "end" of the downloaded log is wall-clock "now" (current time).
- The system fetches the requested number of lines by making sequential paginated API requests (1,000 lines per request, using `end` parameter for backward pagination).
- If fewer lines exist than requested, the user gets whatever is available.
- The download file contains **raw log messages only** (no timestamps).
- File format: plain text, one message per line.
- Filename: `device-{name}-logs-{timestamp}.log`
- The download is constructed client-side: backfill the viewer with the requested data, then build the file from the buffered log entries.

## Technical Context

- Hook: `src/hooks/use-device-logs.ts` — manages SSE streaming + history fetch with a reducer pattern.
- Viewer: `src/components/devices/device-logs-viewer.tsx` — terminal-style log display with auto-scroll.
- API: `GET /api/devices/{device_id}/logs?end=<ISO>` — returns up to 1,000 entries backward from `end`, with `has_more`, `window_start`, `window_end` fields.
- Dialog pattern: Radix UI `Dialog` from `@/components/primitives/dialog`.
- Icon library: `lucide-react` (`Download` icon).
