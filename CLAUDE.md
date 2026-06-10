# Repo conventions for Claude

## Response style

- Keep responses short. No filler, no recap of what the user just said.
- No reasoning narration. Don't explain how you'll approach the problem before doing it.
- Direct language. Skip hedges ("I think...", "perhaps...", "let me...").
- Lead with the answer or the action. Background only if asked.

## Adding new resources

All new domain resources (entity + CRUD + tests) must go through the
`scaffold-resource` skill (`.claude/skills/scaffold-resource/SKILL.md`).
It captures the standard pattern — pagination, auth deps, audit columns,
soft delete, migration numbering, test scaffolding — and runs `pytest` +
`ruff` before returning.

Trigger it with phrases like *"scaffold a new resource"* or
*"add CRUD for &lt;name&gt;"*.
