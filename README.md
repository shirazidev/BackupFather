# backupfather

> *"I'm gonna make your database an offer it can't refuse."*

A production-ready, containerized **PostgreSQL backup tool**. It dumps one or
more databases on a schedule (or on demand), compresses and optionally encrypts
the dump, delivers it to pluggable destinations (**Telegram**, **Bale**,
**Email/SMTP**, local disk), sends success/failure notifications, and enforces a
local retention policy — all driven entirely by environment variables and shipped
as a single Docker image.

Built plugin-first (strategy pattern) so adding a destination (S3, Google Drive,
Discord, …) means writing one class, not touching the core.

---

## Quickstart

### Local, with a throwaway Postgres

```bash
cp .env.example .env
docker compose up --build
# dumps appdb every 5 min into ./backups; health at http://localhost:8080/healthz
```

### Against an external Postgres (the realistic case)

```bash
cp .env.example .env      # fill in real DATABASES + destination credentials
docker compose -f docker-compose.external.yml up -d --build
```

### One-shot (CI / manual / external cron)

```bash
docker compose run --rm backupfather run --once
```

### From source (development)

```bash
uv sync                          # or: python -m venv .venv && pip install -e .[zstd]
uv run backupfather run --once
uv run pytest
```

---

## Architecture

```text
                         ┌──────────────┐
   env vars ─▶ config ─▶ │ BackupRunner │  (orchestrator, depends on ABCs only)
   (pydantic,fail-fast)  └──────┬───────┘
                                │
        ┌───────────────┬───────┴────────┬──────────────┬───────────────┐
        ▼               ▼                ▼              ▼               ▼
   BackupSource   BackupProcessor   BackupDestination  Notifier      retention
   (pg_dump)      (compress,        (telegram, bale,   (telegram,    (local
                   encrypt)          email, local)      email)        cleanup)
```

* **`BackupSource`**, **`BackupProcessor`**, **`BackupDestination`**, **`Notifier`**
  are ABCs. New integrations subclass; core code never changes (Open/Closed).
* Config is validated at startup and the app **fails fast** (exit code 2) with a
  clear message if anything required is missing.
* Every external call (pg_dump, bot APIs, SMTP) is wrapped with retry + timeout +
  clear logging. **Secrets are never logged.**

Pipeline per database: `dump → compress → (encrypt) → deliver → retention → notify`.
One database failing never aborts the others.

---

## Configuration

All configuration is via environment variables (see [`.env.example`](.env.example)).

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASES` | — (required) | `name:dsn,name:dsn`. Names are alphanumeric/`-`/`_`. |
| `PG_DUMP_FORMAT` | `custom` | `custom` (`-Fc`), `plain` (`.sql`), or `directory`. |
| `SCHEDULER_ENABLED` | `true` | `false` → use external cron + `run --once`. |
| `BACKUP_CRON` | `0 3 * * *` | Cron expression, **UTC**. |
| `COMPRESSION` | `gzip` | `gzip`, `zstd` (needs `[zstd]` extra), or `none`. |
| `COMPRESSION_LEVEL` | `6` | gzip 1–9, zstd 1–22. |
| `ENCRYPTION_ENABLED` | `false` | Enable dump encryption. |
| `ENCRYPTION_METHOD` | `gpg` | `gpg` (public key) or `aes` (AES-256 passphrase). |
| `GPG_RECIPIENT` | — | Required when method is `gpg`. |
| `AES_PASSPHRASE` | — | Required when method is `aes`. |
| `DESTINATIONS` | — | Comma list: `telegram,bale,email,local`. |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | Required for `telegram`. |
| `TELEGRAM_MAX_UPLOAD_MB` | `50` | Files above this are auto-split into parts. |
| `BALE_BOT_TOKEN` / `BALE_CHAT_ID` | — | Required for `bale`. |
| `BALE_MAX_UPLOAD_MB` | `50` | Verify Bale's real limit (often lower). |
| `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` | — / `587` | SMTP server. Port `465` = implicit SSL. |
| `SMTP_FROM` / `SMTP_TO` | — | Sender / comma-separated recipients. |
| `SMTP_USE_TLS` | `true` | STARTTLS when not using implicit SSL. |
| `SMTP_MAX_ATTACHMENT_MB` | `20` | Larger dumps skip email (flagged as failure). |
| `NOTIFY_ON_SUCCESS` / `NOTIFY_ON_FAILURE` | `true` / `true` | Toggle notifications. |
| `NOTIFIER_TELEGRAM_CHAT_ID` | — | Send status pings here (reuses bot token). |
| `NOTIFIER_EMAIL_ENABLED` | `false` | Also email status (reuses SMTP settings). |
| `RETENTION_DAYS` | `14` | Delete local backups older than N days. |
| `RETENTION_COUNT` | — | Keep only the newest N local backups per DB. |
| `LOCAL_BACKUP_DIR` | `/backups` | Where dumps are written. |
| `LOG_LEVEL` | `INFO` | Standard log levels. |
| `LOG_FORMAT` | `text` | `text` or `json` (for log aggregators). |
| `HEALTHCHECK_ENABLED` | `true` | Enable `/healthz` HTTP endpoint. |
| `HEALTHCHECK_PORT` | `8080` | Port for `/healthz`. |

Filenames are UTC and filesystem-safe, e.g.
`taxpanel_prod_2026-07-01T03-00-00Z.dump.gz`.

Exit codes: `0` success · `1` runtime failure · `2` configuration error.

---

## How to add a new destination

1. Create `backupfather/destinations/<name>.py` with a class subclassing
   `BackupDestination` and implementing `deliver(artifact, caption)`:

   ```python
   from backupfather.destinations.base import BackupDestination
   from backupfather.models import BackupArtifact, DeliveryResult

   class S3Destination(BackupDestination):
       name = "s3"

       def deliver(self, artifact: BackupArtifact, caption: str) -> DeliveryResult:
           # upload artifact.path ... raise DeliveryError on hard failure
           return DeliveryResult(destination=self.name, ok=True, detail="uploaded")

       def supports_remote_retention(self) -> bool:
           return True  # if the backend can list/delete old objects
   ```

2. Register a builder in `backupfather/destinations/registry.py`:

   ```python
   _BUILDERS["s3"] = lambda s: S3Destination(bucket=s.s3_bucket, ...)
   ```

3. Add any new settings to `config.py` and `.env.example`. Add it to
   `DESTINATIONS`. Add tests mocking the network layer.

The runner, CLI, and scheduler need **no changes**. Notifiers follow the same
pattern via `notifiers/registry.py`.

---

## Known limitations

* **Telegram/Bale ~50 MB upload limit.** Oversized dumps are automatically split
  into numbered parts (`part 1/3`, …). Reassemble with `cat file.part*of* > file`.
  Bale's real limit may be lower — confirm and set `BALE_MAX_UPLOAD_MB`.
* **Email attachment size.** Dumps over `SMTP_MAX_ATTACHMENT_MB` are skipped and
  reported as a delivery failure; use a storage destination for large DBs.
* **Remote retention is not automated.** Telegram, Bale and Email expose no
  list/delete API, so retention applies to **local disk only**. For lifecycle
  management use S3/MinIO with bucket policies (recommended for anything beyond
  small/casual DBs).
* **`pg_dump` version compatibility.** `pg_dump` must be **≥ the target server's
  major version**. The image ships `postgresql-client-16` (`ARG PG_MAJOR=16`);
  rebuild with `--build-arg PG_MAJOR=17` (etc.) for a newer server.
* **Encryption needs `gpg`** in the image (included). AES-256 is implemented via
  `gpg --symmetric --cipher-algo AES256`.

---

## Non-goals (v1)

* Not a full backup orchestration platform — no web UI/dashboard.
* Not point-in-time recovery. This is **logical `pg_dump` backup** only;
  WAL archiving / `pg_basebackup` is a documented future extension, not built here.
* Remote chat/email destinations are delivery & notification channels, **not** a
  substitute for real backup storage with lifecycle management. For production
  data of any size, S3 + real retention is the recommended path.

---

## Development

```bash
uv run pytest                          # 56 tests, all HTTP/SMTP/subprocess mocked
uv run ruff check . && uv run black --check .
```

Tests never hit real databases, bot APIs, or mail servers.
