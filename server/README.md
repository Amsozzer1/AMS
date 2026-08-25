# amsx — the Brain (server)

Python app that automates the Bambu external-spool swap over MQTT. Package layout mirrors the
domain model in [../docs/10-domain-model.md](../docs/10-domain-model.md).

## Package layout (`amsx/`)

Read top to bottom: each layer may import anything below it and nothing above it. That rule is
enforced by `import-linter`, not by review — see [../docs/rules/01-separation-of-concerns.md](../docs/rules/01-separation-of-concerns.md).

| Package | Holds |
|---|---|
| `system/` | Where the app runs: `brain.py` (composition root), `__main__.py`, `middlewares/` (the `Depends` providers), and `infra/` — the adapters, by protocol: `http/`, `mqtt/`, `ftps/` |
| `routes/` | One module per resource, each an `APIRouter`. Mounted by `system/infra/http/app.py` |
| `apps/` | The domain. Each app is `service.py` (logic) + `view.py` (its wire shapes): `printer/` (+ `drivers.py`), `orchestration/` (the only sentient part), `job/`, `module/`, `inventory/`, `prompt/` |
| `libs/` | Third-party clients — `spoolman/` |
| `events/` | `EventBus` and the typed event payloads |
| `types/` | Value objects, ids, wire shapes, and `protocols.py` — **every swappable seam, in one file** |
| `enums/` | The four `StrEnum`s: `PrinterStage`, `PauseReason`, `ModuleState`, `SwapState` |
| `errors/` | Domain exceptions and the HTTP error classes that carry their own status codes |
| `config/` | `Config` loading (printers, clusters, modules, hub) from `ams.json` |
| `utils/` | The `@todo` decorator (RULE 2) |

Build order follows [../docs/07-v0-plan.md](../docs/07-v0-plan.md).

## Dev setup (toolchain: uv + Ruff + ty + pytest)
```bash
uv sync --extra dev      # create .venv + install deps
uv run ruff check .      # lint
uv run ruff format .     # format
uv run ty check          # type-check
uv run pytest            # tests
```

Copy `config/ams.example.json` → `config/ams.local.json` and fill in your printer serial +
access code (LAN mode). `*.local.json` is gitignored — never commit real access codes.
