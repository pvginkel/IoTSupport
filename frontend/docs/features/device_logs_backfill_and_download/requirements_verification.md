# Requirements Verification: Device Logs Backfill & Download

All 13 functional requirements from Section 1a **PASS**.

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Scrolling to top triggers automatic backfill (infinite scroll, no button) | **PASS** | `device-logs-viewer.tsx:84-101` — `handleScroll` detects `atTop` and calls `fetchOlderLogs()` |
| 2 | Scroll position preserved when older entries prepended | **PASS** | `device-logs-viewer.tsx:105-123` — `useLayoutEffect` keyed on `prependCounter` restores position |
| 3 | No loading indicator during backfill | **PASS** | No UI state change for backfill loading; silent fetch |
| 4 | Buffer limit increased to 10,000; stop loading at limit | **PASS** | `use-device-logs.ts:52` — `MAX_BUFFER_SIZE = 10000`; enforced in PREPEND (line 118) and fetchOlderLogs guard (line 411) |
| 5 | Download button (Download icon) next to streaming status | **PASS** | `device-logs-viewer.tsx:155-163` — lucide `Download` icon button in header |
| 6 | Dialog with line-count options: 100, 500, 1000, 5000, 10000 | **PASS** | `device-logs-download-dialog.tsx:21,171-185` — 5 options rendered |
| 7 | "End" of download is wall-clock "now" | **PASS** | `use-device-logs.ts:489` — `cursor = new Date().toISOString()` |
| 8 | Sequential paginated API calls (1,000/request, backward) | **PASS** | `use-device-logs.ts:482-532` — `fetchLogsForDownload` loop |
| 9 | Fewer lines than requested → get whatever is available | **PASS** | Loop terminates when `has_more` is false; returns collected |
| 10 | Raw log messages only (no timestamps) | **PASS** | `device-logs-download-dialog.tsx:128` — `logs.map(log => log.message).join('\n')` |
| 11 | Plain text, .log extension, one message per line | **PASS** | `device-logs-download-dialog.tsx:55-65` — Blob with `text/plain`, `.log` filename |
| 12 | Filename: device-{name}-logs-{timestamp}.log | **PASS** | `device-logs-download-dialog.tsx:46-49` — `buildFilename` |
| 13 | Download constructed client-side | **PASS** | `device-logs-download-dialog.tsx:109-131` — Blob + URL.createObjectURL |

## Notes

- Playwright specs not yet created (blocked on backend `POST /api/testing/devices/logs/seed` endpoint)
- DevicesPage.ts locator getters for new elements not yet added (part of deferred Slice 4)
