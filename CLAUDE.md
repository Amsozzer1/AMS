# AMS — project rules

**This file is an index, not a rulebook.** Each rule lives in its own file; this points at
them. Read the linked file before acting on a rule — the one-liners here are reminders, not
the rule itself.

---

## ⛔ RULE 0 — [The user decides. Claude builds.](docs/rules/00-user-decides.md)

The user makes every decision — architecture, classes, libraries, layout, naming, scope.
Claude builds **exactly** what it was told to build and never acts on its own proposals.
Proposing is encouraged; acting without explicit approval is a violation.

> Before every edit: *did the user explicitly tell me to do **this specific thing**?*
> **No → stop and ask.**

**Requires explicit approval, every time — no exceptions for size, proximity, or obviousness:**
creating/editing/deleting/moving **any** file · adding or upgrading **any** dependency ·
changing architecture, naming, or a public interface · refactoring, cleanup, or a
"while I was in there" fix · any `git` write (commit, branch, push, history).

**Allowed without asking:** reading, searching, running tests/linters/typecheckers, and
presenting options.

Approval never generalises — a yes to one thing is not a yes to the next.
The eight rationalizations that look like exceptions but aren't are in
[the rule](docs/rules/00-user-decides.md); read it before you argue with this.

## ⛔ RULE 1 — [Separation of concerns](docs/rules/01-separation-of-concerns.md)

One job per file. Every layer depends on the layer below through a **named seam**, never
sideways, never upward, never on a concrete implementation it could depend on abstractly.
Good layering is what keeps a decision reversible.

> *If I wanted to swap this implementation tomorrow, how many files would I touch?*
> **More than one → the layering is wrong.**

## RULE 2 — [Stubs are marked, never improvised](docs/rules/02-stubs.md)

Every not-yet-implemented callable carries the `@todo` decorator from `amsx.utils` — never a
hand-written `raise NotImplementedError`. A `Protocol` method is a contract, not a stub.

---

## Architecture

| Area | Document |
|---|---|
| System / server | [docs/02-architecture.md](docs/02-architecture.md), [docs/10-domain-model.md](docs/10-domain-model.md) |
| Frontend | [docs/frontend/00-architecture.md](docs/frontend/00-architecture.md) |
| Frontend API layer | [docs/frontend/01-api-layer.md](docs/frontend/01-api-layer.md) |
| All design docs | [docs/README.md](docs/README.md) |
