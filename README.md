# AMS-X — Open Modular Filament System for Bambu Lab Printers

> Expandable, multi-printer Automatic Material System that bypasses the 4-slot limit of
> Bambu's stock AMS by automating the external-spool swap over MQTT.
> **Design docs are the source of truth → [docs/](docs/).** Start at [docs/README.md](docs/README.md).

## Status
🚧 **Scaffolding.** Project structure is in place; implementation starts per the v0 plan
([docs/07-v0-plan.md](docs/07-v0-plan.md)), gated on the Phase-0 MQTT spike.

## Repo layout (monorepo)
```
docs/        Design docs (vision, architecture, domain model, hardware, media kit)
server/      The "Brain" — Python app (FastAPI + MQTT). Layout mirrors docs/10-domain-model.md
firmware/    ESP32 cluster-controller firmware (PlatformIO)
hardware/    CAD, wiring, BOM for modules / hub / clusters
deploy/      docker-compose for the CasaOS host (server + Mosquitto broker)
spikes/      Throwaway Phase-0 exploration scripts (MQTT control, 3MF parse, FTPS) — not shipped
```

## Quick map (where things live)
| Concern | Path | Doc |
|---|---|---|
| Decisions / architecture | [docs/](docs/) | 01–05 |
| `Module` contract | `server/src/amsx/module/` | [06](docs/06-module-interface.md) |
| Class/domain model | `server/src/amsx/` | [10](docs/10-domain-model.md) |
| v0 build plan | — | [07](docs/07-v0-plan.md) |
| Hardware BOM | `hardware/` | [08](docs/08-hardware.md) |
| Brand / media kit | [docs/media/](docs/media/) | media |

## Toolchain
- **Server:** Python 3.11+, **uv** (env/deps/lock/run), **Ruff** (lint+format), **ty** (types),
  **pytest**. See [server/README.md](server/README.md).
- **Firmware:** **PlatformIO** (ESP32 / Arduino). See [firmware/cluster-controller/](firmware/cluster-controller/).
- **Deploy:** Docker Compose on the **CasaOS** host (brain + Mosquitto). See [deploy/](deploy/).

## Security
Local-first; the only secrets are printer access codes/serials. They stay out of git via
`.gitignore` + a **gitleaks** pre-commit hook. See [SECURITY.md](SECURITY.md).

## License
TBD — see open question #22 in [docs/05-open-questions.md](docs/05-open-questions.md).
