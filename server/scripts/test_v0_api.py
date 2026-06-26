#!/usr/bin/env python3
"""v0 API test-driver — exercises the whole Brain over HTTP, no printer required.

Point it at a running server (simulate mode) and it walks the v0 money shot end to end:
health -> printer state -> 3MF upload + parse -> inject pause -> human prompt -> answer ->
trip sensor -> resume -> cursor advances, for a two-color print. Each step prints PASS/FAIL
with detail, then a summary, so you can report exactly what worked and what didn't.

Run the server first (note the sim config + simulate mode):

    cd server
    AMSX_SIMULATE=1 AMSX_CONFIG=config/ams.sim.yaml AMSX_PORT=9001 uv run amsx

then, in another terminal:

    cd server
    uv run python scripts/test_v0_api.py            # defaults to http://127.0.0.1:9001
    uv run python scripts/test_v0_api.py --base http://127.0.0.1:9001

Stdlib only — no extra installs. The /sim/* hooks are simulate-mode-only on the server, so
this script can never drive real hardware.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import zipfile

BASE = "http://127.0.0.1:9001"

# ---- tiny HTTP layer (stdlib) --------------------------------------------------------------


class Resp:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self.body = body

    def json(self):
        return json.loads(self.body or b"null")


def _request(method: str, path: str, *, data: bytes | None = None, headers=None) -> Resp:
    url = BASE + path
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return Resp(r.status, r.read())
    except urllib.error.HTTPError as e:  # 4xx/5xx still carry a useful body
        return Resp(e.code, e.read())
    except urllib.error.URLError as e:
        raise SystemExit(
            f"\n  cannot reach {url}: {e.reason}\n  is the server running on {BASE}?"
        ) from None


def get(path: str) -> Resp:
    return _request("GET", path)


def post(path: str) -> Resp:
    return _request("POST", path)


def post_multipart(path: str, filename: str, content: bytes) -> Resp:
    boundary = uuid.uuid4().hex
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return _request("POST", path, data=body, headers=headers)


def sliced_3mf(*changes: int) -> bytes:
    """Minimal sliced .gcode.3mf: one `M1020 S<n>` + `M400 U1` per color change."""
    lines = ["; sim test print", "G28", "M104 S210"]
    for n in changes:
        lines += [f"M1020 S{n}", "M400 U1", "G1 X10 Y10 E5"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Metadata/plate_1.gcode", "\n".join(lines) + "\n")
    return buf.getvalue()


# ---- result tracking -----------------------------------------------------------------------

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f"  — {detail}"
    print(line)
    return ok


# ---- the swap-loop driver (mirrors the orchestrator's needs) -------------------------------


def drive_until(pid: str, target_cursor: int, *, budget: int = 600) -> dict:
    """Answer every pending human prompt, and trip the printer sensor once the swap reaches
    SENSING, until the cursor hits ``target_cursor`` (or the orchestrator safe-holds)."""
    for _ in range(budget):
        for p in get("/api/prompts").json():
            post(f"/api/prompts/{p['id']}/answer")
        st = get(f"/api/printers/{pid}/orchestrator").json()
        if st.get("swap_state") == "SENSING":
            post(f"/api/printers/{pid}/sim/sensor?present=true")
        if st.get("cursor") == target_cursor or st.get("held"):
            return st
        time.sleep(0.02)
    return get(f"/api/printers/{pid}/orchestrator").json()


# ---- the test run --------------------------------------------------------------------------


def run() -> int:
    print(f"\nv0 API test-driver → {BASE}\n" + "-" * 52)

    # 1. health
    h = get("/health")
    health = h.json() if h.status == 200 else {}
    check("health 200 + ok", h.status == 200 and health.get("ok") is True, str(health))
    simulate = bool(health.get("simulate"))
    if not check(
        "server is in simulate mode",
        simulate,
        "rerun with AMSX_SIMULATE=1 AMSX_CONFIG=config/ams.sim.yaml",
    ):
        print("\n  Sim hooks are disabled outside simulate mode — stopping.\n")
        return summary()

    # 2. discover a printer
    printers = get("/api/printers").json()
    if not check("at least one printer is configured", bool(printers), str(printers)):
        return summary()
    pid = printers[0]["id"]
    print(f"  using printer: {pid!r}")

    # 3. detail view + no secret leak
    d = get(f"/api/printers/{pid}/detail")
    detail = d.json() if d.status == 200 else {}
    check("printer detail 200", d.status == 200)
    check("access code never serialised", "access_code" not in (d.body or b"").decode().lower())
    check("detail reports connected (sim link)", detail.get("connected") is True)

    # 4. bad 3MF -> 400
    bad = post_multipart(f"/api/printers/{pid}/job", "bad.gcode.3mf", b"not a zip")
    check("bad 3MF rejected with 400", bad.status == 400, f"got {bad.status}")

    # 5. upload a real 2-color sliced 3MF -> parsed plan
    up = post_multipart(f"/api/printers/{pid}/job", "two-color.gcode.3mf", sliced_3mf(0, 1))
    plan = up.json().get("planned_swaps", []) if up.status == 200 else []
    check("3MF upload + parse 200", up.status == 200, up.body.decode()[:120])
    check(
        "plan has 2 swaps with indices [0, 1]",
        [s["filament_index"] for s in plan] == [0, 1],
        str(plan),
    )

    # 6. orchestrator armed
    st = get(f"/api/printers/{pid}/orchestrator").json()
    check(
        "orchestrator armed at cursor 0",
        st.get("armed") is True and st.get("cursor") == 0 and st.get("total") == 2,
        str(st),
    )

    # 7. THE MONEY SHOT — drive both color changes through the closed loop over HTTP
    print("  -- money shot: pause -> prompt -> answer -> sensor -> resume --")
    ok_loop = True
    for target in (1, 2):
        pause = post(f"/api/printers/{pid}/sim/pause")
        if pause.status != 200:
            check(f"inject pause for swap {target}", False, pause.body.decode()[:160])
            ok_loop = False
            break
        st = drive_until(pid, target)
        moved = st.get("cursor") == target and not st.get("held")
        check(
            f"swap {target} completed (cursor→{target}, not held)",
            moved,
            f"cursor={st.get('cursor')} held={st.get('held')} alerts={st.get('alerts')}",
        )
        ok_loop = ok_loop and moved
        if not moved:
            break
    if ok_loop:
        final = get(f"/api/printers/{pid}/orchestrator").json()
        check(
            "print finished — all swaps done, never held",
            final.get("done") is True and final.get("held") is False,
            str(final),
        )

    # 8. the safe-hold path: a pause whose tag doesn't match the plan must NOT swap
    post_multipart(f"/api/printers/{pid}/job", "reset.gcode.3mf", sliced_3mf(0, 1))  # fresh arm
    post(f"/api/printers/{pid}/sim/pause?tag=NOT-OUR-TAG")
    st = drive_until(pid, target_cursor=99, budget=120)  # never reached; expect a hold
    check(
        "stray/mismatched pause safe-holds (no swap)",
        st.get("held") is True and st.get("cursor") == 0,
        f"held={st.get('held')} cursor={st.get('cursor')}",
    )

    return summary()


def summary() -> int:
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("-" * 52)
    print(f"  {passed}/{total} checks passed")
    if passed != total:
        print("  failed:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"    - {name}" + (f": {detail}" if detail else ""))
    print()
    return 0 if passed == total else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Drive the v0 Brain API end to end (simulate mode).")
    ap.add_argument("--base", default=BASE, help=f"server base URL (default {BASE})")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")
    sys.exit(run())
