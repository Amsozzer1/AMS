> One rule per file. Indexed from [CLAUDE.md](../../CLAUDE.md), which is loaded every session.

# RULE 2 — Stubs are marked, never improvised

**Every not-yet-implemented function or method is marked with the `@todo` decorator from
`amsx.utils` — never a hand-written `raise NotImplementedError`.**

```python
from amsx.utils import todo

@todo
def request_unload(self) -> Report: ...

@todo("why / where it's tracked, e.g. PHASE-0, docs/10 #10/#11")
def request_start_print(self, remote_path: str) -> Report: ...
```

Why: stubs then fail *loudly* (calling one logs a warning and raises `NotImplementedError`
naming the callable), are greppable in one place (`@todo` / `__todo__`), and carry their
reason inline. The decorator lives in `server/src/amsx/utils/` and works on sync and async
callables. A `Protocol` method is a *contract*, not a stub — do not decorate it.
