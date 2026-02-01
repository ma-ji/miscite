# Deployment

## Docker Compose (recommended)

```bash
cp .env.example .env
# edit .env
# required for production: OPENROUTER_API_KEY, Mailgun keys, Turnstile keys
mkdir -p data
docker compose up -d --build
```

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

- `bash scripts/backup-data.sh`: backup `./data` (excludes `./data/cache`).
- `bash scripts/restore-data.sh ./backups/<file>.tar.gz --force`: restore `./data`.

## Monitoring

See `deploy/monitoring.md` for uptime and log options.
