# Running backupfather in production

This guide covers deploying backupfather against a **real, external PostgreSQL**
(managed DB, another server, or a Coolify/Docker host) — the common client case.

- [Running backupfather in production](#running-backupfather-in-production)
  - [1. Before you start](#1-before-you-start)
  - [2. Get the image](#2-get-the-image)
  - [3. Configure `.env`](#3-configure-env)
  - [4. Deployment options](#4-deployment-options)
    - [4a. Docker Compose (internal scheduler)](#4a-docker-compose-internal-scheduler)
    - [4b. External cron / `--once`](#4b-external-cron----once)
    - [4c. Kubernetes CronJob](#4c-kubernetes-cronjob)
    - [4d. Coolify](#4d-coolify)
  - [5. Monitoring \& alerting](#5-monitoring--alerting)
  - [6. Restoring a backup](#6-restoring-a-backup)
  - [7. Security checklist](#7-security-checklist)
  - [8. Upgrades](#8-upgrades)
  - [9. Production recommendations](#9-production-recommendations)

---

## 1. Before you start

Check these once per deployment:

- **`pg_dump` ≥ server major version.** The image ships `postgresql-client-16`.
  If the target server is Postgres 17+, build/pull a matching variant:
  ```bash
  docker buildx build --build-arg PG_MAJOR=17 -t ghcr.io/shirazidev/backupfather:0.1.0-pg17 --push .
  ```
- **Network reachability.** The container must reach the DB host:port. For a DB
  on the same Docker host use the host's LAN IP or `host.docker.internal`, not
  `localhost` (that's the container itself).
- **A least-privilege DB role.** Create a read-only-ish backup role rather than
  using the superuser (see §7).
- **Persistent volume for `/backups`.** Retention and the "local copy" only work
  if `/backups` survives container restarts.

---

## 2. Get the image

Pull the published multi-arch image:

```bash
docker pull ghcr.io/shirazidev/backupfather:0.1.0
```

Pin an explicit version tag in production (not `latest`) so redeploys are
reproducible.

---

## 3. Configure `.env`

Copy [`.env.example`](../.env.example) to `.env` and fill it in. A minimal
production `.env` backing up one DB to Telegram + keeping local copies:

```dotenv
DATABASES=prod:postgres://backup_ro:SUPERSECRET@db.internal:5432/appdb
PG_DUMP_FORMAT=custom

SCHEDULER_ENABLED=true
BACKUP_CRON=0 3 * * *          # 03:00 UTC daily

COMPRESSION=gzip
COMPRESSION_LEVEL=6

DESTINATIONS=telegram,local
TELEGRAM_BOT_TOKEN=123456:AA...
TELEGRAM_CHAT_ID=-1001234567890

NOTIFY_ON_FAILURE=true
NOTIFIER_TELEGRAM_CHAT_ID=-1001234567890   # ping this chat on success/failure

RETENTION_DAYS=14
LOCAL_BACKUP_DIR=/backups

LOG_FORMAT=json                # easier to ship to Loki/Datadog/etc.
HEALTHCHECK_ENABLED=true
HEALTHCHECK_PORT=8080
```

> **Secrets:** keep `.env` at `chmod 600`, never commit it, and prefer Docker/
> Coolify/K8s secret stores over a plaintext file where available. backupfather
> never logs secrets, even at debug level.

**Timezone note:** `BACKUP_CRON` is evaluated in **UTC**. `0 3 * * *` = 03:00 UTC.
For Tehran (UTC+3:30) that's 06:30 local — adjust the cron accordingly.

---

## 4. Deployment options

### 4a. Docker Compose (internal scheduler)

The container stays running and fires backups on `BACKUP_CRON`. Use the provided
[`docker-compose.external.yml`](../docker-compose.external.yml):

```bash
BACKUPFATHER_IMAGE=ghcr.io/shirazidev/backupfather:0.1.0 \
  docker compose -f docker-compose.external.yml up -d

docker compose -f docker-compose.external.yml logs -f     # watch it
```

`restart: unless-stopped` is already set, so it survives host reboots.

### 4b. External cron / `--once`

Prefer this if you'd rather not run a long-lived process. Set
`SCHEDULER_ENABLED=false` and trigger one-shot runs from the host's crontab:

```cron
# /etc/crontab — 03:00 UTC daily
0 3 * * * root docker run --rm --env-file /opt/backupfather/.env \
  -v /opt/backupfather/backups:/backups \
  ghcr.io/shirazidev/backupfather:0.1.0 run --once >> /var/log/backupfather.log 2>&1
```

`run --once` exits `0` on success, `1` on runtime failure, `2` on config error —
so cron/monitoring can detect failures from the exit code.

### 4c. Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backupfather
spec:
  schedule: "0 3 * * *"          # UTC
  concurrencyPolicy: Forbid       # never overlap runs
  jobTemplate:
    spec:
      backoffLimit: 1
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: backupfather
              image: ghcr.io/shirazidev/backupfather:0.1.0
              args: ["run", "--once"]
              envFrom:
                - secretRef:
                    name: backupfather-env    # holds DATABASES, tokens, etc.
              volumeMounts:
                - name: backups
                  mountPath: /backups
          volumes:
            - name: backups
              persistentVolumeClaim:
                claimName: backupfather-backups
```

Set `SCHEDULER_ENABLED=false` in the secret — Kubernetes owns the schedule.

### 4d. Coolify

1. New Resource → **Docker Image** → `ghcr.io/shirazidev/backupfather:0.1.0`.
2. Add the environment variables from your `.env` (mark tokens/passwords as
   secrets).
3. Add a **persistent volume** mounted at `/backups`.
4. Expose port `8080` and set the health check path to `/healthz`.
5. Keep `SCHEDULER_ENABLED=true` so the container self-schedules, or set it
   `false` and use a Coolify scheduled task running `run --once`.

---

## 5. Monitoring & alerting

- **`/healthz`** returns `200` when the last run of every DB succeeded, `503`
  once any DB is degraded, and `200` before the first run (startup). Point an
  uptime monitor (UptimeRobot, Coolify health check, k8s probe) at it:
  ```bash
  curl -s localhost:8080/healthz | jq
  # {"status":"ok","databases":{"prod":{"ok":true,"size_mb":12.4,...}}}
  ```
- **Failure notifications**: set `NOTIFY_ON_FAILURE=true` +
  `NOTIFIER_TELEGRAM_CHAT_ID` (and/or `NOTIFIER_EMAIL_ENABLED=true`). Failure
  messages include the DB, the failed step, and a short error — full stack
  traces stay in the logs only.
- **Logs**: set `LOG_FORMAT=json` and ship stdout to your aggregator. Each run
  logs the dump, compression, per-destination delivery, and retention actions.

⚠️ **`/healthz` reflects only the last run while the process is alive.** For the
`--once`/CronJob model, monitor the **exit code** and the failure notification
instead — a crashed container has no endpoint to scrape.

---

## 6. Restoring a backup

backupfather uses `pg_dump`; restore with the standard Postgres tools. Always
test restores periodically — an untested backup is not a backup.

**Custom format** (`PG_DUMP_FORMAT=custom`, the default) → `pg_restore`:

```bash
gunzip -k prod_2026-07-01T03-00-00Z.dump.gz          # -> .dump
pg_restore --clean --if-exists --no-owner \
  -d "postgres://user:pass@host:5432/target_db" \
  prod_2026-07-01T03-00-00Z.dump
```

**Plain format** (`PG_DUMP_FORMAT=plain`) → pipe SQL into `psql`:

```bash
gunzip -c prod_2026-07-01T03-00-00Z.sql.gz | psql "postgres://user:pass@host:5432/target_db"
```

**Chunked files** (Telegram/Bale split a large dump into `.partNNofM`) →
reassemble first, in order:

```bash
cat prod_2026-07-01T03-00-00Z.dump.gz.part*of* > prod.dump.gz
gunzip prod.dump.gz && pg_restore -d "$DSN" prod.dump
```

**Encrypted files** (`.gpg`) → decrypt first:

```bash
gpg --output prod.dump.gz --decrypt prod.dump.gz.gpg   # AES prompts for passphrase
```

---

## 7. Security checklist

- **Least-privilege DB role.** A dump needs read on the data; create a dedicated
  role and avoid the superuser:
  ```sql
  CREATE ROLE backup_ro LOGIN PASSWORD '...';
  GRANT CONNECT ON DATABASE appdb TO backup_ro;
  GRANT USAGE ON SCHEMA public TO backup_ro;
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_ro;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO backup_ro;
  ```
- **TLS to the DB** where possible — append `?sslmode=require` to the DSN.
- **Container runs non-root** (user `bfather`, uid 10001) by default.
- **Restrict `/healthz`** to your monitoring network; it exposes DB names and
  sizes (no secrets, but still metadata).
- **Encrypt off-site copies.** If dumps leave your infrastructure (chat/email),
  enable `ENCRYPTION_ENABLED=true` so the file is unreadable in transit/at rest.
- **Lock down `.env`** (`chmod 600`, owned by the deploy user).

---

## 8. Upgrades

```bash
docker pull ghcr.io/shirazidev/backupfather:0.2.0
# bump the tag in compose / k8s / Coolify, then:
docker compose -f docker-compose.external.yml up -d
```

Pin explicit versions and read the release notes before bumping. Config is
backward-compatible within a major version; new env vars have safe defaults.

---

## 9. Production recommendations

- **Add real object storage for anything beyond small/casual DBs.** Telegram,
  Bale and Email are convenient delivery/notification channels, **not** backup
  storage with lifecycle management — and their retention can't be automated
  (no list/delete API). Use S3/MinIO with a bucket lifecycle policy as the
  primary store; use chat/email as a secondary "did it run?" signal.
- **Keep a local copy** (`local` in `DESTINATIONS` + a persistent `/backups`
  volume) so `RETENTION_*` has something to manage and you have a fast local
  restore path.
- **This is logical backup only.** For low-RPO / point-in-time recovery, pair it
  with WAL archiving / `pg_basebackup` — out of scope for backupfather.
- **Test restores on a schedule**, not just when disaster strikes.
