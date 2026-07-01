# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage: install dependencies into a virtualenv using uv (fast resolver).
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS build

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# uv is distributed as a static binary; copy it from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
RUN python -m venv "$VIRTUAL_ENV"

# Install deps first (cached layer), then the project.
COPY pyproject.toml README.md ./
COPY backupfather ./backupfather
RUN uv pip install --python "$VIRTUAL_ENV/bin/python" .

# ---------------------------------------------------------------------------
# Final stage: slim runtime with postgresql-client for pg_dump.
#
# pg_dump must be >= the target server's major version. We pin the PostgreSQL
# APT repo to a single client major (16) — the common current default. To back
# up a newer server, bump PG_MAJOR here. See README "pg_dump compatibility".
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ARG PG_MAJOR=16
ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    LOCAL_BACKUP_DIR=/backups

# Install pg_dump (postgresql-client-$PG_MAJOR) + gnupg (for optional encryption)
# from the official PGDG repo, then strip apt caches to keep the image small.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates gnupg curl; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt $(. /etc/os-release && echo "$VERSION_CODENAME")-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}"; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
COPY backupfather /app/backupfather
WORKDIR /app

# Non-root user; owns the backup volume.
RUN useradd --system --create-home --uid 10001 backup \
    && mkdir -p /backups \
    && chown -R backup:backup /backups /app
USER backup

VOLUME ["/backups"]
EXPOSE 8080

# Healthcheck hits the in-container /healthz endpoint.
HEALTHCHECK --interval=1m --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; \
u='http://127.0.0.1:8080/healthz'; \
sys.exit(0 if urllib.request.urlopen(u,timeout=4).status==200 else 1)" || exit 1

ENTRYPOINT ["backupfather"]
CMD ["serve"]
