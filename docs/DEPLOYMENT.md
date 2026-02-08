# Deployment

## Docker Compose (recommended)

```bash
cp .env.example .env
# edit .env (set strong POSTGRES_PASSWORD and required API keys)
# required for production: OPENROUTER_API_KEY, Mailgun keys, Turnstile keys
mkdir -p data backups
docker compose up -d --build
```

Compose services now include:

- `db` (PostgreSQL)
- `migrate` (one-shot `alembic upgrade head`, with pre-migration backup when pending)
- `web`
- `worker`

`web`/`worker` are gated on successful migration completion.

## Reverse proxy

### Caddy (automatic TLS)

```bash
docker compose -f docker-compose.yml -f docker-compose.caddy.yml up -d --build
```

Edit `deploy/Caddyfile` to set the domain before starting.

### nginx on host

```bash
DOMAIN=your.domain bash scripts/install-nginx.sh
```

Keep `MISCITE_TRUST_PROXY=true` and `MISCITE_COOKIE_SECURE=true` when terminating TLS at
the proxy.

## systemd (optional)

`deploy/miscite.service` can be installed under `/etc/systemd/system` for auto-start.
If you use Caddy, set `COMPOSE_FILES` in the unit to include `docker-compose.caddy.yml`
(the bootstrap script writes this automatically).

## Backups

- `bash scripts/backup-data.sh`: backup PostgreSQL (`pg_dump`) + `./data` payload
  (excludes `./data/cache` and raw `./data/postgres`).
- `bash scripts/restore-data.sh ./backups/<file>.tar.gz --force`: restore PostgreSQL + payload.
- `scripts/bootstrap-vps-ubuntu.sh` installs a daily systemd timer
  (`miscite-backup.timer`) that runs `scripts/backup-data.sh`.

Pre-migration backups:

- Docker migration runs store timestamped pre-upgrade DB dumps under `./backups/pre-migration`
  by default (`MISCITE_MIGRATE_BACKUP_*`).

## Monitoring

See `deploy/monitoring.md` for uptime and log options.
