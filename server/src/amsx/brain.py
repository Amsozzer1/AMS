"""Brain — the application root (docs/10-domain-model.md).

One per install. Loads `Config`, brings printers + modules online, and owns the orchestrators.
It wires the *real* layer classes together against the shared protocols, so the only thing
"fake" in v0 is the actuator (`ManualModule`) and — until the v0.2 spike confirms MQTT — the
transport (simulate mode).

`PromptBroker` turns a `ManualModule`'s blocking stdin prompt into an async request the HTTP
API can answer, which is exactly the v0 money-shot: server prompts the human, human swaps,
server resumes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from .config import Config, load_config
from .events import EventBus
from .inventory import FakeSpoolStore, SpoolStore
from .inventory.resolver import ProposedRow, Resolver
from .job import Job, JobParser
from .module import Cluster, ManualModule, Module, ModuleRegistry
from .orchestration import Orchestrator
from .printer import Printer
from .printer.drivers import A1Driver, PrinterDriver, X1P1Driver
from .transport import (
    FtpClient,
    FtpsClient,
    MqttBus,
    MqttPrinterLink,
    PrinterLink,
    SimulatedFtpClient,
    SimulatedPrinterLink,
)
from .types import ModuleId, PrinterId

log = logging.getLogger("amsx.brain")


def default_config_path() -> Path:
    """AMSX_CONFIG, else config/ams.local.yaml if present, else the committed example."""
    env = os.getenv("AMSX_CONFIG")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[2]  # .../server
    local = here / "config" / "ams.local.yaml"
    return local if local.exists() else here / "config" / "ams.example.yaml"


def _make_driver(model: str) -> PrinterDriver:
    # Normalise: "A1 mini", "a1-mini", "a1_mini" all collapse to the A1 family.
    m = model.lower().replace(" ", "-").replace("_", "-")
    if m in ("x1", "x1c", "x1-carbon", "p1", "p1p", "p1s"):
        return X1P1Driver()
    if m in ("a1", "a1-mini", "a1mini"):
        return A1Driver()
    raise ValueError(f"unknown printer model {model!r} (expected x1|p1|a1|a1-mini)")


class PendingPrompt:
    """A human action the orchestrator is waiting on (surfaced over HTTP)."""

    def __init__(self, prompt_id: str, module_id: ModuleId, message: str) -> None:
        self.id = prompt_id
        self.module_id = module_id
        self.message = message
        self.future: asyncio.Future[str] = asyncio.get_event_loop().create_future()


class PromptBroker:
    """Bridges `ManualModule`'s async prompter to the API. `ask` blocks the swap until the
    human answers via `answer`. This is the v0 stand-in for module hardware.
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingPrompt] = {}
        self._counter = 0

    def prompter_for(self, module_id: ModuleId):
        async def _prompter(message: str) -> str:
            return await self.ask(module_id, message)

        return _prompter

    async def ask(self, module_id: ModuleId, message: str) -> str:
        self._counter += 1
        prompt_id = f"p{self._counter}"
        pending = PendingPrompt(prompt_id, module_id, message)
        self._pending[prompt_id] = pending
        log.info("PROMPT %s [module %s]: %s", prompt_id, module_id, message)
        try:
            return await pending.future
        finally:
            self._pending.pop(prompt_id, None)

    def answer(self, prompt_id: str, response: str = "done") -> bool:
        pending = self._pending.get(prompt_id)
        if pending is None:
            return False
        log.info("PROMPT %s answered (module %s): %s", prompt_id, pending.module_id, response)
        if not pending.future.done():
            pending.future.set_result(response)
        return True

    def pending(self) -> list[dict]:
        return [
            {"id": p.id, "module_id": p.module_id, "message": p.message}
            for p in self._pending.values()
        ]


class Brain:
    """Application root: config + buses + printers + modules + orchestrators."""

    def __init__(self, config: Config, *, simulate: bool = True) -> None:
        self.config = config
        self.simulate = simulate
        self.events = EventBus()
        self.prompts = PromptBroker()

        self.printers: dict[PrinterId, Printer] = {}
        self.clusters: dict[str, Cluster] = {}
        self.registry: ModuleRegistry | None = None
        self.orchestrators: dict[PrinterId, Orchestrator] = {}

        # Spool inventory: populated in __init__ from config; tests may replace brain.store before
        # start() is called.  assignment maps printer_id -> {filament_index -> ProposedRow}.
        # Use the property setter so resolver is always built from the current store.
        self._store: SpoolStore = FakeSpoolStore()
        self.resolver: Resolver = Resolver(self._store)
        self.assignment: dict[PrinterId, dict[int, ProposedRow]] = {}
        # confirmed tracks which printers have had their job/assignment POST-confirmed.
        self.confirmed: set[PrinterId] = set()

        self._module_by_id: dict[ModuleId, Module] = {}
        self._printer_buses: dict[PrinterId, MqttBus] = {}
        self._started = False

    # ---- store property: setter rebuilds resolver ----
    @property
    def store(self) -> SpoolStore:
        return self._store

    @store.setter
    def store(self, value: SpoolStore) -> None:
        self._store = value
        self.resolver = Resolver(value)

    # ---- lifecycle ----
    async def start(self) -> None:
        """Bring printers + modules online. Idempotent."""
        if self._started:
            return
        self._bring_up_modules()
        await self._bring_up_printers()
        # Ensure Spoolman has the custom field we need before any swap; SOFT (logs on error).
        await self.store.ensure_module_field()
        self._started = True
        log.info(
            "Brain started (simulate=%s): %d printer(s), %d module(s), %d cluster(s)",
            self.simulate,
            len(self.printers),
            len(self._module_by_id),
            len(self.clusters),
        )

    async def stop(self) -> None:
        for bus in self._printer_buses.values():
            disconnect = getattr(bus, "disconnect", None)
            if disconnect is None:
                continue
            try:
                disconnect()
            except Exception:  # best-effort teardown
                log.warning("printer bus disconnect failed", exc_info=True)
        self._printer_buses.clear()
        self._started = False

    def _bring_up_modules(self) -> None:
        modules: list[Module] = []
        index_map: dict[int, ModuleId] = {}
        for mc in self.config.modules:
            mod = ManualModule(mc.id, prompter=self.prompts.prompter_for(mc.id))
            modules.append(mod)
            self._module_by_id[mc.id] = mod
            if mc.filament_index is not None:
                index_map[mc.filament_index] = mc.id
        self.registry = ModuleRegistry(modules, index_map)
        for cc in self.config.clusters:
            cmods = [self._module_by_id[mid] for mid in cc.module_ids if mid in self._module_by_id]
            self.clusters[cc.id] = Cluster(cc.id, cmods)

    async def _bring_up_printers(self) -> None:
        for pc in self.config.printers:
            link: PrinterLink
            ftp: FtpClient
            if self.simulate:
                link = SimulatedPrinterLink(pc.id, pc.serial)
                ftp = SimulatedFtpClient()
            else:
                # PHASE-0: each Bambu printer runs its OWN broker (TLS 8883, access-code auth);
                # confirm host/port/topic semantics in the v0.2 spike before trusting this path.
                pbus = MqttBus(host=pc.ip, port=8883)
                pbus.connect(access_code=pc.access_code)
                self._printer_buses[pc.id] = pbus
                link = MqttPrinterLink(pbus, pc.id, pc.serial)
                ftp = FtpsClient(pc.ip, pc.access_code)
            printer = Printer(pc.id, link, _make_driver(pc.model), self.events, ftp)
            await printer.connect()
            self.printers[pc.id] = printer

    # ---- the front-end entry point ----
    async def arm_job(self, printer_id: PrinterId, file: str | Path) -> Orchestrator:
        """Parse a sliced 3MF and arm the orchestrator for the swaps — WITHOUT pushing/starting.

        This is the FTPS-free path: the operator starts the print themselves (Bambu Studio / SD)
        while the Brain owns the swap loop from the pause onward. ``submit_job`` is this plus the
        (still hardware-unverified) FTPS push + start-print.
        """
        printer = self.printers.get(printer_id)
        if printer is None:
            raise KeyError(f"unknown printer {printer_id!r}")
        if self.registry is None:
            raise RuntimeError("Brain not started")

        plan = JobParser().parse(Job(file=file, printer_id=printer_id))
        # Re-arming a printer: detach the previous orchestrator from the bus FIRST, or it keeps
        # hearing pauses and the swap runs twice (duplicate prompts — observed live 2026-06-25).
        previous = self.orchestrators.pop(printer_id, None)
        if previous is not None:
            previous.unsubscribe()
            log.info("re-arming %s: detached previous orchestrator", printer_id)
        orch = Orchestrator(printer, plan, self.registry, self.events, printer_id=printer_id)
        orch.subscribe()
        self.orchestrators[printer_id] = orch
        # New job: clear any previous confirmation so the operator must re-confirm.
        self.confirmed.discard(printer_id)
        # Compute a best-effort spool proposal for the operator; cached until re-arm.
        try:
            self.assignment[printer_id] = await self.resolver.propose(plan)
        except Exception:
            log.warning("resolver.propose failed for %s (soft)", printer_id, exc_info=True)
            self.assignment.setdefault(printer_id, {})
        log.info("job armed on %s: %d planned swap(s)", printer_id, len(plan))
        return orch

    async def submit_job(self, printer_id: PrinterId, file: str | Path) -> Orchestrator:
        """Arm the plan, then push the sliced 3MF (FTPS) and start the print over MQTT.

        The push/start half is the v0.4 hardware-unverified path; use ``arm_job`` to drive the
        swap loop against an externally-started print.
        """
        orch = await self.arm_job(printer_id, file)
        printer = self.printers[printer_id]
        path = await printer.send_job(str(file))
        await printer.start_print(path)
        log.info("job submitted + started on %s", printer_id)
        return orch


def build_brain(config_path: str | Path | None = None, *, simulate: bool = True) -> Brain:
    """Construct (not yet start) a Brain from a config file."""
    config = load_config(config_path or default_config_path())
    brain = Brain(config, simulate=simulate)
    if not simulate and config.spoolman.enabled:
        from .inventory.spoolman import SpoolmanStore

        brain.store = SpoolmanStore(config.spoolman)
    else:
        brain.store = FakeSpoolStore()
    # brain.store setter already rebuilds brain.resolver — no extra step needed.
    return brain
