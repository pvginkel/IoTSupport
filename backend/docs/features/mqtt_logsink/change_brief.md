# Change Brief: MQTT Log Sink

## Summary

Replace the current Logstash-based log ingestion pipeline with an MQTT-based log sink built directly into this application. The application will subscribe to an MQTT topic, receive device log messages, and forward them to Elasticsearch.

## Current State

Devices send logs to Logstash via HTTP (port 9001, JSON lines format). Logstash strips ANSI escape codes and writes to Elasticsearch with index pattern `logstash-http-YYYY.MM.dd`.

## Desired State

This application subscribes to MQTT topic `iotsupport/logsink` and:
1. Receives JSON log messages (same payload format as current HTTP endpoint)
2. Strips ANSI escape codes from the `message` field
3. Adds current timestamp (ignores any `relative_time` field in payload)
4. Writes to Elasticsearch using the same index pattern `logstash-http-YYYY.MM.dd`

## Key Requirements

- **MQTT Persistent Sessions**: Use persistent sessions so Mosquitto queues messages while the app is down. Client ID configurable via environment variable with default `iotsupport-logsink`.
- **QoS 1**: Subscribe with QoS 1 (at least once delivery).
- **No Batching**: Write each message to Elasticsearch immediately upon receipt.
- **Retry on ES Failure**: If Elasticsearch write fails, retry indefinitely with exponential backoff (1s initial delay, +1s per retry, max 60s between retries). At most one message is lost on crash.
- **Graceful Shutdown**: Integrate with the shutdown coordinator to stop processing cleanly.

## Out of Scope

- Batching/bulk writes (may add later if needed)
- Exactly-once delivery guarantees
- Changes to the existing `ElasticsearchService` (read-only, for querying logs)
