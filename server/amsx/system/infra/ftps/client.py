"""FtpClient implementations — uploading the sliced .gcode.3mf, real and simulated.

Both satisfy the ``FtpClient`` protocol from ``amsx.types``.
"""

from __future__ import annotations

import asyncio
import ftplib
import logging
import ssl

from amsx.system.infra.ftps.tls import _ImplicitFTPTLS
from amsx.types import PrinterId

log = logging.getLogger("amsx.system.infra.ftps")

__all__ = ["FtpsClient", "SimulatedFtpClient"]


class FtpsClient:
    """Real implicit-FTPS upload of the sliced job to a Bambu printer over the LAN.

    How Bambu's file transfer works (confirmed pattern, Doridian/OpenBambuAPI + community):
    the printer runs an **implicit**-FTPS server on port 990 — TLS from the first byte — with
    user ``bblp`` and the LAN access code as the password; the cert is self-signed (we don't
    verify it — the link is LAN-local and access-code-gated). Sliced ``.3mf`` files go in the
    printer's ``/cache`` directory, and the print is then started over MQTT with
    ``project_file`` referencing ``ftp:///cache/<name>`` (the empty-host triple slash is just
    ``ftp://`` + the absolute ``/cache/...`` path). So ``upload`` returns ``/cache/<name>`` and
    the driver wraps it ``ftp://`` → ``ftp:///cache/<name>``.

    ``ftplib`` is blocking, so the transfer runs in a worker thread.

    PHASE-0 (v0.4) — implemented to the documented convention but **not yet run against our
    A1**: the remaining hardware item is simply confirming the A1 accepts this upload +
    ``project_file`` start. The dir (``/cache``) and url form are the documented norm.
    """

    PORT = 990
    USER = "bblp"
    CACHE_DIR = "/cache"  # Bambu stores sliced jobs here; start_print references ftp:///cache/...

    def __init__(self, host: str, access_code: str, *, timeout: float = 30.0) -> None:
        self.host = host
        self._access_code = access_code  # secret: never log
        self._timeout = timeout

    async def upload(self, printer: PrinterId, file: str) -> str:
        """Upload ``file`` into the printer's ``/cache`` and return the path start_print uses."""
        name = file.rsplit("/", 1)[-1]
        await asyncio.to_thread(self._upload_blocking, file, name)
        remote = f"{self.CACHE_DIR}/{name}"
        # Log the path only — never the access code.
        log.info("FtpsClient: uploaded %s to printer %s", remote, printer)
        return remote

    def _upload_blocking(self, file: str, name: str) -> None:
        # Self-signed cert -> unverified context. Bambu's FTPS stack is old, so relax the
        # OpenSSL security level enough for its cert/ciphers to negotiate.
        ctx = ssl._create_unverified_context()
        try:
            ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        except ssl.SSLError:  # pragma: no cover - depends on the local OpenSSL build
            pass

        ftp = _ImplicitFTPTLS(context=ctx, timeout=self._timeout)
        # Log every phase so a hang points at the exact step (the last line before it stalls),
        # rather than a bare "read operation timed out" with no context. No secrets are logged.
        try:
            log.info("FTPS %s:%d — connecting (implicit TLS)…", self.host, self.PORT)
            ftp.connect(self.host, self.PORT)
            log.info("FTPS %s — connected; authenticating as %r…", self.host, self.USER)
            ftp.login(self.USER, self._access_code)
            ftp.prot_p()  # encrypt the data channel too (Bambu requires it)
            log.info("FTPS %s — authenticated; entering %s…", self.host, self.CACHE_DIR)
            # Drop the file in /cache (where Bambu keeps sliced jobs). The dir exists on stock
            # firmware; create it defensively in case a wipe removed it.
            try:
                ftp.cwd(self.CACHE_DIR)
            except ftplib.error_perm:  # pragma: no cover - depends on the live printer
                ftp.mkd(self.CACHE_DIR)
                ftp.cwd(self.CACHE_DIR)
            log.info("FTPS %s — storing %r…", self.host, name)
            with open(file, "rb") as fh:
                ftp.storbinary(f"STOR {name}", fh)
            log.info("FTPS %s — stored %s/%s ✓", self.host, self.CACHE_DIR, name)
        finally:
            try:
                ftp.quit()
            except ftplib.all_errors:  # quit can fail if the link is already gone
                ftp.close()


class SimulatedFtpClient:
    """In-memory FtpClient for tests: records uploads, returns a deterministic remote path."""

    def __init__(self) -> None:
        self.uploaded: list[tuple[PrinterId, str]] = []

    async def upload(self, printer: PrinterId, file: str) -> str:
        self.uploaded.append((printer, file))
        name = file.rsplit("/", 1)[-1]
        return f"/cache/{name}"
