#!/usr/bin/env python3
"""FTPS upload DIAGNOSIS — gather evidence on WHY STOR hangs (don't fix yet).

The minimal probe (ftps_probe.py) proved: control channel + LIST (download) work, but STOR
(upload) times out reading the 226 after sending data. We already avoid ``conn.unwrap()``
(the issue-31727 fix), so unwrap is NOT our cause. This script isolates the real asymmetry by
capturing, per trial, two decisive facts:

  1. the NEGOTIATED TLS version on the control AND data sockets, and
  2. whether the bytes actually LAND in /cache (checked on a FRESH connection with SIZE),
     which separates "transfer failed" from "only the 226 ack failed".

It runs the same STOR twice — once with the default TLS context, once forced to TLS 1.2 — so we
can see whether the version is what flips a plain-close from "226 withheld" to "226 returned".

    cd server
    uv run python ../spikes/ftps_diag.py
"""

from __future__ import annotations

import ftplib
import io
import socket
import ssl
import time
from collections.abc import Callable
from pathlib import Path

from amsx.config import load_config
from amsx.transport import _ImplicitFTPTLS

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "server" / "config" / "ams.local.yaml"
NAME = "amsx_diag.txt"
PAYLOAD = b"amsx ftps diagnosis payload\n"  # len() printed below


class _Instrumented(_ImplicitFTPTLS):
    """Captures the data-channel socket so we can read its negotiated TLS version."""

    last_data_version: str | None = None

    def ntransfercmd(self, cmd: str, rest: object = None):
        conn, size = super().ntransfercmd(cmd, rest)
        try:
            self.last_data_version = conn.version()  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            self.last_data_version = "?"
        return conn, size


# ---- STOR strategies (the data-socket shutdown is the variable under test) -----------------
def stor_plainclose(ftp: _Instrumented, name: str, data: bytes) -> str:
    """Current behaviour: send, plain close, no TLS close_notify (FTP.storbinary equivalent)."""
    ftp.voidcmd("TYPE I")
    with ftp.transfercmd(f"STOR {name}") as conn:
        conn.sendall(data)
    return ftp.voidresp()


def stor_oneway_shutdown(ftp: _Instrumented, name: str, data: bytes) -> str:
    """Send our close_notify but DON'T wait for the peer's (non-blocking unwrap), then close.

    This signals "upload complete" at the TLS layer so the server commits the file and sends
    226, without blocking on a close_notify reply Bambu may never send.
    """
    ftp.voidcmd("TYPE I")
    with ftp.transfercmd(f"STOR {name}") as conn:
        conn.sendall(data)
        conn.setblocking(False)
        try:
            conn.unwrap()  # writes close_notify; read-of-peer's raises WantRead -> ignored
        except (ssl.SSLWantReadError, ssl.SSLWantWriteError, BlockingIOError, OSError):
            pass
        finally:
            conn.setblocking(True)
    return ftp.voidresp()


def stor_unwrap_shorttimeout(ftp: _Instrumented, name: str, data: bytes) -> str:
    """Full blocking unwrap but with a short data-socket timeout, tolerating the timeout."""
    ftp.voidcmd("TYPE I")
    with ftp.transfercmd(f"STOR {name}") as conn:
        conn.sendall(data)
        conn.settimeout(3.0)
        try:
            conn.unwrap()
        except (TimeoutError, socket.timeout, ssl.SSLError, OSError):
            pass
    return ftp.voidresp()


def stor_via_storbinary(ftp: _Instrumented, name: str, data: bytes) -> str:
    """The real FtpsClient path: ftplib's own storbinary (uses our overridden one)."""
    return ftp.storbinary(f"STOR {name}", io.BytesIO(data))


def _ctx(force_tls12: bool) -> ssl.SSLContext:
    ctx = ssl._create_unverified_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    if force_tls12:
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _connect(ip: str, code: str, ctx: ssl.SSLContext) -> _Instrumented:
    ftp = _Instrumented(context=ctx, timeout=15)
    ftp.connect(ip, 990)
    ftp.login("bblp", code)
    ftp.prot_p()
    return ftp


def _readback_fresh(ip: str, code: str) -> bytes | None:
    """Open a brand-new connection and DOWNLOAD /cache/NAME back (the download path works).

    Returns the exact bytes the server persisted (None if the file isn't there). A full
    round-trip is the strongest proof the upload committed correctly.
    """
    ftp = _connect(ip, code, _ctx(False))
    try:
        ftp.cwd("/cache")
        names = ftp.nlst()
        if NAME not in names and f"/cache/{NAME}" not in names:
            return None
        buf = io.BytesIO()
        ftp.retrbinary(f"RETR {NAME}", buf.write)
        return buf.getvalue()
    except ftplib.error_perm:
        return None
    finally:
        try:
            ftp.quit()
        except ftplib.all_errors:
            ftp.close()


StorFn = Callable[[_Instrumented, str, bytes], str]


def trial(ip: str, code: str, label: str, stor: StorFn) -> None:
    print(f"\n========== TRIAL: {label} ==========", flush=True)

    # Pre-clean so the read-back check afterward is unambiguous.
    try:
        pre = _connect(ip, code, _ctx(False))
        try:
            pre.delete(f"/cache/{NAME}")
            print("pre-clean: deleted stale /cache file")
        except ftplib.error_perm:
            print("pre-clean: no stale file")
        finally:
            pre.quit()
    except ftplib.all_errors as exc:
        print(f"pre-clean skipped: {type(exc).__name__}: {exc}")

    ftp = _connect(ip, code, _ctx(False))
    ftp.cwd("/cache")  # faithful to the real FtpsClient: store INTO /cache

    t0 = time.monotonic()
    err: str | None = None
    try:
        resp = stor(ftp, NAME, PAYLOAD)
        print(f"STOR -> {resp!r} in {time.monotonic() - t0:.1f}s")
    except Exception as exc:  # noqa: BLE001 - we want every failure mode
        err = f"{type(exc).__name__}: {exc}"
        print(f"STOR raised after {time.monotonic() - t0:.1f}s: {err}")
    print(f"data TLS version: {ftp.last_data_version}")
    try:
        ftp.quit()
    except ftplib.all_errors:
        ftp.close()

    # The decisive question: did the bytes actually land, regardless of the 226?
    got = _readback_fresh(ip, code)
    if got is None:
        print(f"VERDICT: file ABSENT → bytes did NOT commit (err={err})")
    elif got == PAYLOAD:
        ok = "and 226 returned ✓✓" if err is None else f"but STOR raised (err={err})"
        print(
            f"VERDICT: file PRESENT, {len(got)} bytes, content MATCHES → COMMITTED {ok}"
        )
    else:
        print(
            f"VERDICT: file PRESENT but {len(got)} bytes / content differs → TRUNCATED (err={err})"
        )


def main() -> int:
    pc = load_config(CONFIG).printers[0]
    print(
        f"diagnosing FTPS upload on {pc.id} — {pc.ip}:990  (payload {len(PAYLOAD)} bytes)"
    )
    trials: list[tuple[str, StorFn]] = [
        ("plain-close (current)", stor_plainclose),
        ("ftplib storbinary (real client path)", stor_via_storbinary),
        ("one-way close_notify", stor_oneway_shutdown),
        ("unwrap + 3s timeout", stor_unwrap_shorttimeout),
    ]
    for label, fn in trials:
        try:
            trial(pc.ip, pc.access_code, label, fn)
        except ftplib.all_errors as exc:
            print(f"TRIAL aborted: {type(exc).__name__}: {exc}")
    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
