#!/usr/bin/env python3
"""FTPS upload INTEGRITY check — is the file we STOR byte-identical on the printer?

The upload now returns 226, but the A1 mini throws "micro SD card read/write exception" when it
tries to PRINT the file — i.e. it can't read our file back off the card. Prime suspect: our
skip-unwrap plain close truncates/corrupts larger uploads (the 28-byte test was too small to
show it). This round-trips real-sized payloads through OUR FtpsClient and compares MD5 up vs down:

  1. a 2 MB random binary (maximally sensitive to any truncation/corruption), and
  2. an existing Studio-uploaded .3mf already on the printer (re-upload under a test name,
     download both, compare) — a real sliced job the firmware is known to accept.

    cd server
    uv run python scripts/check_ftps_integrity.py
"""

from __future__ import annotations

import asyncio
import ftplib
import hashlib
import io
import os
import ssl
import tempfile
from pathlib import Path

from amsx.config import load_config
from amsx.transport import FtpsClient, _ImplicitFTPTLS

REPO = Path(__file__).resolve().parents[1]
CONFIG = REPO / "server" / "config" / "ams.local.yaml"


def _ctx() -> ssl.SSLContext:
    ctx = ssl._create_unverified_context()
    try:
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx


def _connect(ip: str, code: str) -> _ImplicitFTPTLS:
    ftp = _ImplicitFTPTLS(context=_ctx(), timeout=30)
    ftp.connect(ip, 990)
    ftp.login("bblp", code)
    ftp.prot_p()
    return ftp


def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def _download(ftp: _ImplicitFTPTLS, remote: str) -> bytes:
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {remote}", buf.write)
    return buf.getvalue()


def _delete(ftp: _ImplicitFTPTLS, remote: str) -> None:
    try:
        ftp.delete(remote)
    except ftplib.all_errors:
        pass


async def roundtrip(ip: str, code: str, src_bytes: bytes, label: str) -> None:
    print(f"\n=== {label} — {len(src_bytes)} bytes, src md5={_md5(src_bytes)} ===")
    name = f"amsx_integ_{label}.bin"
    with tempfile.NamedTemporaryFile(suffix=".gcode.3mf", delete=False) as f:
        f.write(src_bytes)
        local = f.name
    try:
        # Upload via the REAL production client (exercises the skip-unwrap storbinary).
        client = FtpsClient(ip, code)
        # FtpsClient stores under the file's basename; rename our temp so it's predictable.
        target = Path(local).with_name(name)
        os.rename(local, target)
        local = str(target)
        remote = await client.upload("Bedroom", local)
        print(f"uploaded -> {remote}")

        ftp = _connect(ip, code)
        try:
            got = _download(ftp, remote)
            print(f"downloaded {len(got)} bytes, md5={_md5(got)}")
            if got == src_bytes:
                print("RESULT: ✓ identical — upload is lossless")
            else:
                n = min(len(got), len(src_bytes))
                first = next((i for i in range(n) if got[i] != src_bytes[i]), n)
                print(
                    f"RESULT: ✗ DIFFERS — len {len(src_bytes)}->{len(got)}, "
                    f"first diff at byte {first}"
                )
            _delete(ftp, remote)
        finally:
            ftp.quit()
    finally:
        try:
            os.unlink(local)
        except OSError:
            pass


async def main() -> int:
    pc = load_config(CONFIG).printers[0]
    print(f"integrity check on {pc.id} — {pc.ip}")

    # 1) 2 MB of random bytes — any corruption/truncation shows up immediately.
    await roundtrip(pc.ip, pc.access_code, os.urandom(2 * 1024 * 1024), "rand2mb")

    # 2) A real Studio-sliced .3mf already on the printer (known-good print job).
    ftp = _connect(pc.ip, pc.access_code)
    try:
        ftp.cwd("/cache")
        names = ftp.nlst()
        sample = next((n for n in names if n.endswith(".3mf") and not n.startswith("amsx")), None)
        real = _download(ftp, sample) if sample else None
    finally:
        ftp.quit()
    if real is not None:
        await roundtrip(pc.ip, pc.access_code, real, "real3mf")
    else:
        print("\n(no existing .3mf in /cache to round-trip)")

    print("\ndone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
