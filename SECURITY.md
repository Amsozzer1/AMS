# Security & Secrets

AMS-X is **local-first** (LAN mode, no Bambu cloud). The only secrets are **printer access
codes / serials** (and later any Spoolman/remote-access tokens). They must never enter git.

## Where secrets live (all gitignored)
| Secret | Put it in | Ignored by |
|---|---|---|
| Printer serial + access code | `server/config/ams.local.json` **or** `.env` | `*.local.json`, `.env` |
| WiFi creds (firmware) | PlatformIO build flags from an untracked file | `.env`, build-flag file |
| Any keys/certs | `secrets/` | `secrets/`, `*.pem`, `*.key` |

Committed files use **placeholders only** (`REPLACE_ME`): `server/config/ams.example.json`,
`.env.example`.

## Defense in depth (active now)
1. **`.gitignore`** excludes `*.local.json`, `.env`, `secrets/`, keys/certs.
2. **pre-commit + gitleaks** — `.pre-commit-config.yaml` scans every commit and **blocks**
   anything that looks like a secret (plus `detect-private-key`). Enable once:
   ```bash
   pip install pre-commit && pre-commit install
   pre-commit run --all-files   # optional first sweep
   ```
3. **App loads secrets from env / local file**, never hard-coded.

## Broker note
`deploy/mosquitto/mosquitto.conf` allows anonymous access on the **LAN only**. Before exposing
the broker or dashboard beyond the LAN, switch Mosquitto to authenticated access
(`password_file` + ACLs) and put the dashboard behind the reverse proxy / tunnel.

## If a secret is ever committed
Rotate it immediately (regenerate the printer access code in LAN settings), then purge it from
history (`git filter-repo` / BFG) before pushing anywhere.
