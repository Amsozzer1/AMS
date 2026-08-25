> One rule per file. Indexed from [CLAUDE.md](../../CLAUDE.md), which is loaded every session.

# ⛔ RULE 1 — SEPARATION OF CONCERNS ⛔
### (SECOND ONLY TO RULE 0)

**Every file does one job. Every layer depends on the layer below it through a named seam —
never sideways, never upward, and never on a concrete implementation when it could depend on
an abstract one.**

## Why this is Rule 1 and not a style preference

Good layering is what turns an **expensive, permanent** decision into a **cheap, reversible**
one. That is the whole point of it.

Worked example — picking native `fetch` over Axios for the frontend HTTP client. If
`client.ts` owns the transport and every other file is *handed* a client, switching to Axios
later is a **30-minute change to one file**. If components call `fetch()` directly and the
layers circle each other, that same switch is effectively impossible, and a decision nobody
thought hard about becomes permanent by accident.

**So: never let a decision leak past the layer that owns it.** A decision that lives in one
file stays reversible forever. A decision that leaks into forty files is final the day it
ships.

This is also why "which library" is usually the *less* important question. Set the layering
up correctly and the library stops being a commitment.

## The worked example — this repo already does it right

`server/amsx/types/protocols.py` is the model to follow — every swappable seam in the system
lives in that one file. The Orchestrator imports **zero** concrete classes, only these seams:

| Seam | Real | Fake / alternate |
|---|---|---|
| `Module` | *(HardwareModule — Phase 1)* | `ManualModule` |
| `PrinterControl` | `Printer` | simulator-backed `Printer` |
| `PrinterLink` | `MqttPrinterLink` | `SimulatedPrinterLink` |
| `FtpClient` | `FtpsClient` | `SimulatedFtpClient` |
| `SpoolStore` | `SpoolmanStore` | `FakeSpoolStore` |
| `PrinterDriver` | `X1P1Driver` | `A1Driver` |

That one discipline is why the entire swap loop was built, tested, and shipped **before a
single motor existed.** Hold the frontend to the same standard.

## The rules

- **Depend on the seam, not the implementation** — a Protocol, an interface, or an injected
  client. Never import a concrete class you could have abstracted.
- **One job per file.** A file that holds types *and* transport *and* routing *and* business
  logic is a god-file. Split it.
- **Dependencies point one direction only.** Down the stack. No cycles, no back-references.
- **No sideways imports between peers.** Peers talk through the layer below, not each other.
- **The consumer never knows the mechanism.** A component knows `API.spools.list()`. It must
  not know the URL, the HTTP verb, the client library, or that HTTP is involved at all.

## The test — before adding any import or file

> **If I wanted to swap this implementation tomorrow, how many files would I have to touch?**
>
> **More than one → the layering is wrong.** Fix the seam, not the call sites.
