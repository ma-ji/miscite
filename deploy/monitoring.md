# Monitoring options (single VPS)

This app does not expose Prometheus metrics yet, but there are several low-effort ways to keep it reliable.

## Health endpoints

- `GET /healthz` — app process is alive.
- `GET /readyz` — app is ready (DB ok, datasets present, LLM key set).

## Suggested options

1) **Simple uptime checks (easy)**
   - Use an external monitor (Uptime Kuma, Healthchecks, StatusCake).
   - Check `https://miscite.review/readyz` every 1–5 minutes.

2) **Docker + systemd**
   - Compose has container healthchecks.
   - Use `systemctl status miscite` (if you enable the systemd unit).
   - `docker ps` shows health status, `docker logs -f <container>`.

3) **Host-level checks**
   - Disk space: ensure `./data` doesn’t fill the volume.
   - Memory: Docling + LLM parsing can be memory-heavy on larger docs.

4) **Log aggregation (optional)**
   - Caddy access logs + Docker logs to a local file or external service.
   - On Ubuntu, `journalctl -u miscite -f` if using systemd.

If you want first-class metrics (Prometheus/Grafana), we can add a `/metrics` endpoint and expose worker counters.
