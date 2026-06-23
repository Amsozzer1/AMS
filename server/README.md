# amsx — the Brain (server)

Python app that automates the Bambu external-spool swap over MQTT. Package layout mirrors the
domain model in [../docs/10-domain-model.md](../docs/10-domain-model.md).

## Package layout (`src/amsx/`)
| Package | Holds (per docs/10) |
|---|---|
| `config/` | `Config` loading (printers, clusters, modules, hub) |
| `transport/` | `MqttBus`, `PrinterLink`, `ClusterLink`, `FtpClient` |
| `printer/` | `Printer`, `PrinterState`; `printer/drivers/` → `PrinterDriver`, `X1P1Driver`, `A1Driver` |
| `job/` | `Job`, `JobParser`, `SwapPlan`, `PlannedSwap` |
| `module/` | `Module` (Manual/Hardware), `Cluster`, `ModuleRegistry` |
| `orchestration/` | `Orchestrator`, `SwapStateMachine`, `SwapContext` — the only sentient part |
| `inventory/` | `Spool`, `SpoolmanClient` (Phase 4) |
| `api/` | FastAPI app + websockets |

> Nothing is implemented yet — these are empty packages. Build order follows
> [../docs/07-v0-plan.md](../docs/07-v0-plan.md) (v0.1 transport → v0.3 printer state →
> v0.4 job → v0.5 module → v0.6 orchestrator).

## Dev setup (toolchain: uv + Ruff + ty + pytest)
```bash
uv sync --extra dev      # create .venv + install deps
uv run ruff check .      # lint
uv run ruff format .     # format
uv run ty check          # type-check
uv run pytest            # tests
```

Copy `config/ams.example.yaml` → `config/ams.local.yaml` and fill in your printer serial +
access code (LAN mode). `*.local.yaml` is gitignored — never commit real access codes.
