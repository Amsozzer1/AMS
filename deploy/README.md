# deploy

Runs the Brain on the **CasaOS** host (Docker-native; no GPIO needed — modules are network
devices over WiFi/MQTT). See locked decision #8 in [docs/README.md](../docs/README.md).

## What's here
- `docker-compose.yml` — **Mosquitto** broker now; the `server` service is commented until the
  app entrypoint exists.
- `mosquitto/mosquitto.conf` — broker config (LAN, anonymous by default — secure before any
  remote exposure).

## Bring up the broker (works today)
```bash
docker compose -f deploy/docker-compose.yml up -d mosquitto
```

## Later
Uncomment the `server` service once `amsx` has a runnable entrypoint, then `up -d`. Remote
access (optional) via a reverse proxy / tunnel (ngrok / Cloudflare / Tailscale) — local-first
by default.
