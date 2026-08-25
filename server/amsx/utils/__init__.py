"""utils — small cross-cutting helpers shared across amsx (no domain logic lives here).

Leaf package: stdlib only, imports nothing from the rest of ``amsx``, so anything may depend
on it without creating a cycle.
"""

from amsx.utils.todo import todo

__all__ = ["todo"]
