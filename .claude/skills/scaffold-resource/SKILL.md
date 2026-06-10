---
name: scaffold-resource
description: |
  Use when the user wants to scaffold a new domain resource (entity + CRUD
  endpoints + tests) in the agentic-ecommerce monorepo. The skill orchestrates
  specialist sub-agents whose briefs live in `prompts/`:

  1. data-modeler   — designs the SQLAlchemy model + Alembic migration
  2. api-designer   — designs the Pydantic schemas + FastAPI router
  3. code-generator — writes all files, runs `pytest` + `ruff`, reports

  (A fourth `fe-code-generator` specialist will plug in here when
  `apps/web/` exists.)

  Each phase pauses for explicit user confirmation BEFORE the next runs.
  No files are written until phase 3.

  Trigger phrases: "scaffold a new resource", "create a new entity",
  "add CRUD for <thing>", "generate endpoints for <thing>",
  "new domain entity", "wire up a new model".
---

# scaffold-resource — orchestrator

You are the orchestrator for a multi-phase resource scaffolding workflow.
The user wants to add a new domain entity (e.g. orders, customers,
addresses, carts) following the repo's standard pattern.

## Hard rules

- Do **not** write any code until phase 3. Phases 1 and 2 produce
  proposals for the user to approve.
- Each phase delegates to a specialist sub-agent via the `Agent` tool
  (`subagent_type: "general-purpose"`).
- For each specialist, **read its prompt file** from `prompts/` and pass
  the file contents — with the placeholders filled in — as the
  sub-agent's `prompt` argument. Don't paraphrase or improvise; the
  prompt files are the source of truth for what each specialist does.
- After every sub-agent returns, summarize its proposal in chat and ask
  the user **"OK to proceed?"**. Don't move on without an explicit yes.
- Final phase must leave the repo green (`pytest` passes, `ruff check`
  clean, `ruff format` clean).

## Specialist prompt files

| Phase | Specialist | Prompt file |
|---|---|---|
| 1 | data-modeler | `prompts/data-modeler.md` |
| 2 | api-designer | `prompts/api-designer.md` |
| 3 | code-generator | `prompts/code-generator.md` |

When you spawn a specialist:

1. `Read` the matching prompt file in full.
2. Fill in every `<placeholder>` with the values gathered so far (user
   inputs + prior-phase outputs).
3. Pass the rendered text as the sub-agent's `prompt`.

## Phase flow

### Phase 1 — Entity definition

**1a.** Ask the user (one consolidated message — don't drip questions):

- Resource name (singular, snake_case, e.g. `order`).
- Fields: for each, name, type, nullable, unique/indexed, default.
- Relationships: foreign keys to existing tables.
- Discriminator/kind enums (like `StoreKind`)? If so, the allowed values.
- Soft delete? (default yes — adds `is_active`.)
- Audit columns? (default yes — `created_by`, `created_at`, `updated_at`.)
- Any CHECK constraints worth enforcing at the DB level.

**1b.** Spawn the **data-modeler** using `prompts/data-modeler.md`.

**1c.** Show the proposal to the user, then ask
*"OK to proceed to phase 2?"*. Loop until yes.

### Phase 2 — Endpoint design

**2a.** Ask the user (one consolidated message):

- Which verbs? Default = list + get + post + patch + delete.
- Per-verb permissions: `ADMIN-only`, `creator-only`,
  `any-authenticated`, or `public` (storefront-style with coarsened data).
- Additional list query params beyond `page`, `limit`?
- Any custom non-CRUD routes? (e.g. `POST /orders/{id}/cancel`.)
- Any public storefront variant under `/storefront/...`?

**2b.** Spawn the **api-designer** using `prompts/api-designer.md`.

**2c.** Show the proposal, then ask
*"OK to proceed to phase 3 (write files + run tests)?"*. Loop until yes.

### Phase 3 — Generate + verify

**3a.** Spawn the **code-generator** using `prompts/code-generator.md`.

**3b.** Print the sub-agent's report plus a one-line summary
(`"X endpoints, Y tests, all green"` or the failure detail). Done.

## Adding a new specialist later

To add (e.g.) a frontend code generator:

1. Drop `prompts/fe-code-generator.md` into the same `prompts/` folder.
2. Add a row to the specialist-prompt table above.
3. Add a phase (or extend phase 3) in the flow section that spawns it.

No other change needed — keeping each specialist in its own file is the
whole point of this layout.
