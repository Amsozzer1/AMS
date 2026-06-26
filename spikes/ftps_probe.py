#!/usr/bin/env python3
"""Probe the Bambu FTPS upload with full protocol tracing — find where STOR hangs.

Connect/auth/cwd already work; the STOR (data channel, opened via PASV) times out. This runs
the same steps with ftplib's debug trace on, so we SEE every command + response and the exact
stall point — especially the ``227 Entering Passive Mode (ip,ip,ip,ip,p,p)`` reply (if the
printer hands back an unreachable data IP, that's the bug). It also tries a LIST first (a
simpler data transfer) to tell "data channel is broken" from "STOR specifically is broken".

Run it in its own terminal (FTPS is separate from the Brain's MQTT, so the backend can stay up):

    cd server
    uv run python ../spikes/ftps_probe.py
"""

from __future__ import annotations

import ftplib
import io
import ssl
from pathlib import Path

from amsx.config import load_config
from amsx.transport import _ImplicitFTPTLS

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "server" / "config" / "ams.local.yaml"


def step(label: str) -> None:
    print(f"\n=== {label} ===", flush=True)


def main() -> int:
    pc = load_config(CONFIG).printers[0]
    print(f"probing FTPS on {pc.id} — {pc.ip}:990 (timeout 20s)")

    ctx = ssl._create_unverified_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass

    ftp = _ImplicitFTPTLS(context=ctx, timeout=20)
    ftp.set_debuglevel(2)  # print every command/response (*cmd*/*put*/*get*/*resp*)

    step("CONNECT")
    ftp.connect(pc.ip, 990)
    step("LOGIN")
    ftp.login("bblp", pc.access_code)
    step("PROT P")
    ftp.prot_p()
    step("PWD")
    print("pwd:", ftp.pwd())

    step("LIST root (data-channel test #1)")
    try:
        lines: list[str] = []
        ftp.retrlines("LIST", lines.append)
        print(f"LIST ok — {len(lines)} entries")
    except Exception as exc:
        print(f"LIST FAILED: {type(exc).__name__}: {exc}")

    step("CWD /cache")
    try:
        ftp.cwd("/cache")
        print("cwd /cache ok; pwd:", ftp.pwd())
    except Exception as exc:
        print(f"CWD /cache FAILED: {type(exc).__name__}: {exc}")

    step("STOR amsx_probe.txt (data-channel test #2)")
    try:
        ftp.storbinary("STOR amsx_probe.txt", io.BytesIO(b"amsx ftps probe\n"))
        print("STOR ok ✓")
    except Exception as exc:
        print(f"STOR FAILED: {type(exc).__name__}: {exc}")

    try:
        ftp.quit()
    except ftplib.all_errors:
        ftp.close()
    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
