# Agentic Driven E-Commerce

Monorepo for a multi-store ecommerce platform — physical points of sale,
platform-owned online storefronts, and user-owned marketplace stores —
built end-to-end as a single coherent codebase.

What lives here:

| Path | Status | What |
|---|---|---|
| `apps/api/` | shipped | FastAPI REST service. JWT auth, RBAC (`ADMIN`, `SELLER`, `VENDOR`, `CUSTOMER`, `GUEST`), products / stores / inventory / public storefront |
| `apps/web/` | planned | Next.js storefront + admin/POS dashboard |
| `packages/shared/` | shipped | Python code shared across apps (config, env loader) |
| Future packages | — | Anything cross-app belongs here (TypeScript clients, design system, shared types, etc.) |

The whole repo is designed to be developed with
**[Claude Code](https://claude.com/claude-code)**. Conventions live in
`CLAUDE.md` and skills under `.claude/skills/` — both are auto-loaded
when you start a Claude Code session in this repo, so the same patterns
get enforced no matter which app you're working in.

---

## Prerequisites

| Tool | Why | Install |
|---|---|---|
| **macOS or Linux** | Untested on Windows | — |
| **Docker** | Local Postgres | https://docs.docker.com/get-docker/ |
| **uv** | Python package manager + venv + runner | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Claude Code** | Required for the scaffolding workflow + repo conventions | https://claude.com/claude-code |

`uv` will install Python 3.13 itself — you don't need a system Python.

Make sure `uv` is on your PATH:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## First-time setup

```bash
# 1. Install dependencies (creates .venv, fetches Python 3.13)
uv sync

# 2. Configure environment
cp .env.example .env
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
# Paste the output into .env, replacing the placeholder JWT_SECRET_KEY value.

# 3. Start Postgres
docker compose up -d postgres

# 4. Run migrations
cd apps/api && uv run alembic upgrade head && cd ../..

# 5. Create an admin user
uv run agentic-ecommerce-create-user alice s3cret --role admin
```

---

## Running the API

```bash
uv run agentic-ecommerce-api
```

The API serves on `http://127.0.0.1:8000`.

| URL | What |
|---|---|
| `/docs` | Swagger UI (interactive; click **Authorize** to attach your bearer token) |
| `/redoc` | ReDoc (read-only docs) |
| `/openapi.json` | Raw OpenAPI 3.1 spec |
| `/health` | Liveness probe |

Quick smoke test from the terminal:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"alice","password":"s3cret"}'

TOKEN="paste-token-here"
curl http://127.0.0.1:8000/auth/me -H "Authorization: Bearer $TOKEN"
```

---

## Using Claude Code in this repo

When you open the repo in Claude Code, two things load automatically:

1. **`CLAUDE.md`** — repo-wide conventions (response style, the scaffolding requirement).
2. **`.claude/skills/`** — skills that Claude can invoke when triggered by your prompts.

You don't need to do anything special — just start a Claude Code session
inside the repo and use the trigger phrases below.

### Available skills

| Skill | Trigger phrases | What it does |
|---|---|---|
| **`scaffold-resource`** | *"scaffold a new resource"*, *"create a new entity"*, *"add CRUD for X"*, *"generate endpoints for X"* | Orchestrates a 3-phase multi-agent workflow that designs a new domain entity, designs its endpoints, then writes all files (model, migration, router, schemas, tests) and runs `pytest` + `ruff` before returning. **This is the required path for adding new domain resources** — it enforces the repo's pagination, auth, and audit-column conventions. |

Skill files live at `.claude/skills/<name>/SKILL.md`. To add a new skill,
drop a new directory there with its own `SKILL.md`.

---

## Repo layout

```
.
├── apps/
│   ├── api/                       # FastAPI service
│   │   ├── alembic/               # DB migrations
│   │   ├── src/agentic_ecommerce_api/
│   │   │   ├── auth/              # JWT + role gates
│   │   │   ├── cli/               # console scripts (create-user, …)
│   │   │   ├── db/                # SQLAlchemy models + session
│   │   │   ├── inventory/         # schemas + service
│   │   │   ├── products/          # schemas + slug helper
│   │   │   ├── routers/           # FastAPI routers (auth, products, stores, inventory, storefront, health)
│   │   │   ├── storefront/        # public coarsened-availability schemas
│   │   │   ├── stores/            # schemas
│   │   │   ├── _pagination.py     # PageParams, Page[T], paginate()
│   │   │   └── main.py            # FastAPI app + tags + Swagger config
│   │   └── tests/                 # pytest suite (SQLite-via-aiosqlite, no live Postgres needed)
│   └── web/                       # Next.js app (placeholder; not built yet)
├── packages/
│   └── shared/                    # agentic_ecommerce_shared — Settings, env loader
├── .claude/
│   └── skills/                    # Claude Code skills (scaffold-resource, …)
├── docker-compose.yml             # local Postgres
├── pyproject.toml                 # uv workspace root
├── CLAUDE.md                      # repo conventions for Claude
└── README.md
```

---

## Common commands

```bash
# Tests
uv run pytest -q                    # full suite
uv run pytest apps/api/tests/test_auth.py -q   # one file
uv run pytest -k "test_login" -q    # by name

# Lint + format
uv run ruff check .
uv run ruff format .

# Migrations
cd apps/api
uv run alembic upgrade head         # apply all
uv run alembic downgrade -1         # roll back one
uv run alembic revision -m "msg"    # new revision (use the scaffold-resource skill instead when adding a resource)
cd ../..

# Create users
uv run agentic-ecommerce-create-user <username> <password> --role admin|seller|vendor|customer

# Stop and wipe local Postgres (loses all data)
docker compose down -v
```

---

## Domain model (current state)

| Resource | Notes |
|---|---|
| **Users** | `ADMIN`, `SELLER`, `VENDOR`, `CUSTOMER` roles; JWT auth |
| **Products** | Global catalog; no stock fields; soft delete |
| **Stores** | `PHYSICAL` (POS), `ONLINE` (platform brand sites, multi-brand), `MARKETPLACE` (vendor-owned). DB CHECK constraints enforce kind-specific required fields |
| **Inventory** | `(product, store)` rows + append-only `InventoryMovement` audit log. ADMIN-writable; any authenticated user can read |
| **Storefront** | Public no-auth coarsened availability for `ONLINE` stores only |

See `/docs` for the live endpoint surface.

---

## Troubleshooting

- **`uv: command not found`** → PATH not set. See Prerequisites.
- **`password authentication failed for user "..."`** → your local `.env` doesn't match `docker-compose.yml`. Update `DATABASE_URL` to use the credentials in `.env.example`.
- **`relation "users" does not exist`** → migrations not applied. `cd apps/api && uv run alembic upgrade head`.
- **`ValidationError: JWT_SECRET_KEY required`** → `.env` doesn't exist or the key is empty. See step 2 of First-time setup.
- **Postgres won't accept new credentials after editing docker-compose** → existing volume keeps the old user. `docker compose down -v` then `docker compose up -d postgres`.
