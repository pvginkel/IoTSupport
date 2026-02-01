# Device Logs Feature - Change Brief

## Summary

Add an endpoint to retrieve device logs from Elasticsearch, enabling the frontend to display a scrolling log window for each device.

## Functional Requirements

### Endpoint

`GET /api/devices/<id>/logs` - Retrieve log entries for a specific device from Elasticsearch.

### Data Source

- **Elasticsearch cluster**: `http://elasticsearch.home`
- **Index pattern**: `logstash-http-*`
- **Timestamp field**: `@timestamp`
- **Device filter**: Match `entity_id` field against the device's `device_entity_id`
- **Return fields**: `@timestamp` (as `timestamp`) and `message`

### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start` | ISO datetime | No | Start of time range (how far back to retrieve). Defaults to "now" |
| `end` | ISO datetime | No | End of time range (for historical/search queries). Defaults to "now" |
| `query` | string | No | Wildcard search pattern to filter on message field |

### Response Format

```json
{
  "logs": [
    {"timestamp": "2026-02-01T14:43:27.948Z", "message": "Log line content..."},
    ...
  ],
  "has_more": true,
  "window_start": "2026-02-01T14:40:00.000Z",
  "window_end": "2026-02-01T14:43:27.948Z"
}
```

### Pagination Behavior

- Maximum 1000 log entries per request
- Results ordered by timestamp ascending (oldest first)
- If more than 1000 results exist in the time range, return `has_more: true`
- Return `window_start` and `window_end` indicating the actual time range covered
- Caller can paginate by adjusting `start` to `window_end` on subsequent requests

### Error Handling

- Return 503 Service Unavailable if Elasticsearch is unreachable
- Return 404 if device not found

### Configuration

Add to environment variables:
- `ELASTICSEARCH_URL` - Elasticsearch base URL
- `ELASTICSEARCH_USERNAME` - Authentication username
- `ELASTICSEARCH_PASSWORD` - Authentication password
- `ELASTICSEARCH_INDEX_PATTERN` - Index pattern (default: `logstash-http-*`)
