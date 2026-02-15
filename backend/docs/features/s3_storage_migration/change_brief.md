# Change Brief: Migrate Firmware and Coredump Storage to S3

Migrate all persistent binary storage from local filesystem directories (`ASSETS_DIR` for firmware, `COREDUMPS_DIR` for coredumps) to S3-compatible object storage, using the existing `S3Service` infrastructure.

## Firmware Storage

Replace filesystem-based firmware storage with S3 objects. Currently firmware is stored as versioned ZIP bundles and a legacy flat binary. In S3, store each build artifact as an individual object under `firmware/{model_code}/{version}/` — no ZIP wrapper, no legacy flat binary.

Add a `MAX_FIRMWARES` environment variable (default 5) to control per-model firmware version retention. When a new firmware is uploaded, prune old versions that exceed the limit. Retention must guard against pruning versions still referenced by unparsed coredumps (`parse_status=PENDING`).

## Coredump Storage

Replace filesystem-based coredump storage with S3 objects keyed as `coredumps/{device_key}/{db_id}.dmp`, where `db_id` is the coredump's database primary key. The current timestamp-based filename generation is eliminated — the database ID is sufficient.

## Sidecar Integration

`PARSE_SIDECAR_XFER_DIR` remains a filesystem path. The coredump parsing thread downloads `.dmp` and `.elf` from S3 to the xfer directory for the sidecar to consume.

## Environment Variables

- Remove: `ASSETS_DIR`, `COREDUMPS_DIR`
- Add: `MAX_FIRMWARES` (int, default 5)
- Keep: `PARSE_SIDECAR_XFER_DIR`, `PARSE_SIDECAR_URL`, `MAX_COREDUMPS` and all S3 config vars

## Migration

Provide a CLI command to migrate existing filesystem data to S3. The migration is a one-time cutover operation run during brief downtime.

## S3 Consistency

All create/delete operations must follow the S3 golden rules defined in CLAUDE.md:
- Creates: S3 upload must succeed before DB commit
- Deletes: DB commit before S3 delete (best-effort)
