"""Brain — the application root (docs/10-domain-model.md).

One per install. Loads `Config`, brings printers + modules online, and owns the orchestrators.
It wires the *real* layer classes together against the shared protocols, so the only thing
"fake" in v0 is the actuator (`ManualModule`) and — until the v0.2 spike confirms MQTT — the
transport (simulate mode).

It owns a `PromptBroker` (see `amsx.apps.prompt`) but defines nothing itself — everything here
is construction and wiring.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

import amsx
from amsx.apps.inventory import FakeSpoolStore, SpoolStore
from amsx.apps.inventory.resolver import ProposedRow, Resolver
from amsx.apps.job import Job, JobParser
from amsx.apps.module import Cluster, ManualModule, Module, ModuleRegistry
from amsx.apps.orchestration import Orchestrator, consume_plan
from amsx.apps.printer import Printer
from amsx.apps.printer.drivers import A1Driver, PrinterDriver, X1P1Driver
from amsx.apps.prompt import PromptBroker
from amsx.config import Config, load_config
from amsx.events import EventBus, FinishedEvent
from amsx.system.infra.ftps import FtpsClient, SimulatedFtpClient
from amsx.system.infra.mqtt import MqttBus, MqttPrinterLink, SimulatedPrinterLink
from amsx.types import FtpClient, ModuleId, PrinterId, PrinterLink

log = logging.getLogger("amsx.system.brain")


def default_config_path() -> Path:
    """AMSX_CONFIG, else config/ams.local.json if present, else the committed example."""
    env = os.getenv("AMSX_CONFIG")
    if env:
        return Path(env)
    # Anchored on the amsx package, NOT on this file's depth: `parents[N]` silently resolves
    # somewhere else the moment this module moves, and it fails as a confusing "file not
    # found" on a path that looks almost right. amsx/__init__.py's parent is always .../server.
    here = Path(amsx.__file__).resolve().parent.parent  # .../server
    local = here / "config" / "ams.local.json"
    return local if local.exists() else here / "config" / "ams.example.json"


def _make_driver(model: str) -> PrinterDriver:
    # Normalise: "A1 mini", "a1-mini", "a1_mini" all collapse to the A1 family.
    m = model.lower().replace(" ", "-").replace("_", "-")
    if m in ("x1", "x1c", "x1-carbon", "p1", "p1p", "p1s"):
        return X1P1Driver()
    if m in ("a1", "a1-mini", "a1mini"):
        return A1Driver()
    raise ValueError(f"unknown printer model {model!r} (expected x1|p1|a1|a1-mini)")


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
        # The sliced file each printer is currently armed with, so the operator can confirm the
        # mapping and THEN start the held job (FTPS upload + start) without re-arming (which would
        # wipe the confirmed assignment). Set by arm_job; consumed by start_armed.
        self._armed_files: dict[PrinterId, str] = {}

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
        # Subscribe to FinishedEvent so we can consume spool grams when a print completes.
        self.events.subscribe(FinishedEvent, self._on_finished)
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
            if self.simulate:
                sim_link: PrinterLink = SimulatedPrinterLink(pc.id, pc.serial)
                sim_ftp: FtpClient = SimulatedFtpClient()
                printer = Printer(pc.id, sim_link, _make_driver(pc.model), self.events, sim_ftp)
                await printer.connect()
                self.printers[pc.id] = printer
                continue

            # Live: an offline / unreachable printer must NOT abort the whole Brain — the
            # dashboard and Spoolman inventory don't need it. Register the printer first, then
            # connect best-effort; on failure log a clear warning and leave it DISCONNECTED (it
            # shows in the UI as offline; a restart brings it up once it's reachable).
            # PHASE-0: each Bambu printer runs its OWN broker (TLS 8883, access-code auth).
            pbus = MqttBus(host=pc.ip, port=8883)
            self._printer_buses[pc.id] = pbus
            printer = Printer(
                pc.id,
                MqttPrinterLink(pbus, pc.id, pc.serial),
                _make_driver(pc.model),
                self.events,
                FtpsClient(pc.ip, pc.access_code),
            )
            self.printers[pc.id] = printer
            try:
                pbus.connect(access_code=pc.access_code)
                await printer.connect()
            except Exception as exc:  # offline printer is non-fatal — boot degraded
                log.warning(
                    "Printer %r unreachable at %s:8883 (%s: %s) — started DISCONNECTED. The "
                    "dashboard and inventory still work; this printer won't be controllable until "
                    "it's reachable (power it on, confirm LAN mode + IP, then restart the server).",
                    pc.id,
                    pc.ip,
                    type(exc).__name__,
                    exc,
                )

    # ---- finish handler: consume spool grams on print completion ----
    async def _on_finished(self, event: FinishedEvent) -> None:
        """On printer FINISHED, decrement spool grams for the completed plan (best-effort, SOFT).

        Builds `assignment` (index→module) and `loaded` (module→spool_id) snapshots, then
        delegates to `consume_plan`. A failed/cancelled print just doesn't consume (acceptable).
        """
        printer_id = event.printer_id
        orch = self.orchestrators.get(printer_id)
        if orch is None:
            return
        per_printer = self.assignment.get(printer_id, {})
        if not per_printer:
            return
        try:
            assignment = {idx: row.module for idx, row in per_printer.items() if row.module}
            spools = await self.store.list_spools()
            # Build store-derived loadout first, then overlay the confirmed assignment rows so
            # a spool that was assigned to a module but not yet reflected in store.list_spools()
            # extra.ams_module (e.g. Spoolman was down when the job started) is not silently
            # skipped — the assignment row already carries its own resolved spool_id.
            loaded: dict[str, str] = {s.module: s.id for s in spools if s.module}
            assignment_loadout = {
                row.module: row.spool_id
                for row in per_printer.values()
                if row.module and row.spool_id
            }
            loaded.update(assignment_loadout)  # assignment rows take precedence
            await consume_plan(self.store, orch.plan, assignment=assignment, loaded=loaded)
            log.info("brain: consumed spool grams for printer %s on FINISH", printer_id)
        except Exception:  # SOFT — consume errors must not surface to the operator
            log.warning("brain: consume_plan failed for %s (soft)", printer_id, exc_info=True)

    def _module_resolver_for(self, printer_id: PrinterId) -> Callable[[int], Module]:
        """Build a ``filament_index -> Module`` resolver for one printer's orchestrator.

        Prefers the operator's CONFIRMED colour→module assignment, falling back to the static
        config registry map. Reads ``self.assignment`` lazily (at swap time), so a confirmation
        POSTed AFTER the job is armed takes effect on the next swap.
        """

        def _resolve(index: int) -> Module:
            assert self.registry is not None  # arm_job guarantees the brain is started
            row = self.assignment.get(printer_id, {}).get(index)
            if row is not None and row.module is not None:
                try:
                    return self.registry.by_id(row.module)
                except KeyError:
                    pass  # assigned module not in the registry → fall back
            return self.registry.for_filament_index(index)

        return _resolve

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
        orch = Orchestrator(
            printer,
            plan,
            self.registry,
            self.events,
            printer_id=printer_id,
            module_resolver=self._module_resolver_for(printer_id),
        )
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
        # Remember the file so start_armed can push+start it after the operator confirms.
        self._armed_files[printer_id] = str(file)
        log.info("job armed on %s: %d planned swap(s)", printer_id, len(plan))
        return orch

    async def start_armed(self, printer_id: PrinterId) -> None:
        """Push (FTPS) + start the job this printer is ALREADY armed with — no re-arm.

        Lets the operator confirm the colour→module mapping first, then start, without
        re-parsing/re-proposing (which would wipe the confirmed assignment). Raises KeyError if
        nothing is armed for the printer.
        """
        file = self._armed_files.get(printer_id)
        if file is None:
            raise KeyError(f"no armed job for printer {printer_id!r} — upload (arm) one first")
        printer = self.printers[printer_id]
        path = await printer.send_job(file)
        await printer.start_print(path)
        log.info("armed job started on %s", printer_id)

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
        from amsx.libs.spoolman import SpoolmanStore

        brain.store = SpoolmanStore(config.spoolman)
    else:
        brain.store = FakeSpoolStore()
    # brain.store setter already rebuilds brain.resolver — no extra step needed.
    return brain
