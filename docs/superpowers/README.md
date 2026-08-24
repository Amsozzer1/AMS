# superpowers — the planning workflow

The plans and specs in this folder are produced by the **superpowers** plugin. It was an
undeclared ambient dependency on one laptop until this file existed: the plans said
`REQUIRED SUB-SKILL: superpowers:subagent-driven-development`, but nothing in the repo said
what that was, where it came from, or what version. Anyone landing here cold — human or
agent — could not reproduce the loop.

## The dependency

| | |
|---|---|
| Plugin | `superpowers` |
| Marketplace | `claude-plugins-official` |
| Pinned in | [`.claude/settings.json`](../../.claude/settings.json) → `enabledPlugins` |

It is declared in **project** settings, so it travels with the repo like any other
dependency. Verify with `/plugin` in Claude Code.

## The loop

```
   spec  ──▶  plan  ──▶  execute task-by-task  ──▶  archive
    │          │              │                        │
 specs/     plans/      one subagent per task     plans/archive/
```

1. **Spec** (`specs/`) — the design decision and its rationale, written *before* any plan.
   Edge cases and locked choices live here so a plan never has to re-litigate them.
2. **Plan** (`plans/`) — dated `YYYY-MM-DD-<slug>.md`, broken into numbered Tasks with
   `- [ ]` checkboxes. Each task carries its own tests and constraints, so it can be handed
   to a subagent with no other context. Written with `superpowers:writing-plans`.
3. **Execute** — `superpowers:subagent-driven-development` (in-session) or
   `superpowers:executing-plans` (separate session). One task per subagent, tested
   individually. **RULE 0 still binds every subagent** — see
   [`docs/rules/00-user-decides.md`](../rules/00-user-decides.md) and the rules block at the
   top of each file in [`.claude/agents/`](../../.claude/agents).
4. **Archive** — see below.

## Plan lifecycle (decided — apply it, don't invent a new one)

**Plans are historical records, not living checklists.** A plan describes what was decided
at a point in time; the code and git history describe what is true now.

- **While in flight:** the plan stays in `plans/` and its checkboxes are ticked as tasks land.
- **On completion:** move it to `plans/archive/`, tick every box, and add a completion header
  naming the **commit range** that implemented it.
- **If abandoned:** move it to `plans/archive/` with a header saying so and why. Do not
  silently delete it — the reasoning is the value.

**Why this matters:** an unchecked box in a shipped plan is worse than no plan. Any agent
reading `plans/` treats it as pending work and will happily re-plan something that shipped a
month ago. `plans/` must only ever contain work that is genuinely not done.
