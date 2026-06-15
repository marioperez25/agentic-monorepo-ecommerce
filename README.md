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
| **Docker** | Runs Postgres locally in a container | https://docs.docker.com/get-docker/ |
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
# 1. Install Python deps (creates .venv, fetches Python 3.13)
uv sync

# 2. Configure environment
cp .env.example .env
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
# Paste the output into .env, replacing the placeholder JWT_SECRET_KEY value.

# 3. Start Postgres (Docker container, runs in the background)
docker compose up -d postgres

# 4. Run migrations
cd apps/api && uv run alembic upgrade head && cd ../..

# 5. Create an admin user
uv run agentic-ecommerce-create-user alice s3cret --role admin
```

After step 5 the stack is fully provisioned. Move to *Running the API*.

---

## Local database

Postgres runs in a Docker container defined by `docker-compose.yml` at
the repo root. **Tests don't need it** — the pytest suite uses an
in-memory SQLite database via `aiosqlite`, so `uv run pytest` works
whether the container is up or not. The container is needed when you
run the API itself.

| Setting | Value |
|---|---|
| Image | `postgres:17-alpine` |
| Container name | `agentic-ecommerce-postgres` |
| Host port | `5432` → container `5432` |
| Database / user / password | `agentic_ecommerce` / `agentic_ecommerce` / `agentic_ecommerce` |
| Data volume | `postgres_data` (named volume, persists across `docker compose down` — wiped only by `down -v`) |

Daily lifecycle:

```bash
docker compose up -d postgres        # start in background
docker compose ps                    # status (look for "healthy")
docker compose logs -f postgres      # tail logs
docker compose stop postgres         # stop, keep container + data
docker compose start postgres        # bring it back up
docker compose down                  # stop + remove container (data survives in volume)
docker compose down -v               # stop + remove container + WIPE the volume
```

Connect directly with `psql`:

```bash
docker exec -it agentic-ecommerce-postgres \
  psql -U agentic_ecommerce -d agentic_ecommerce

# inside psql:
\dt              # list tables
\d users         # describe the users table
SELECT * FROM users LIMIT 5;
\q               # quit
```

---

## Environment variables

The API reads `.env` at the repo root (gitignored — never commit it).
Copy `.env.example` and fill in the values below.

| Variable | Required | Default | What |
|---|---|---|---|
| `DATABASE_URL` | yes | — | SQLAlchemy async URL. The default in `.env.example` matches the `docker-compose.yml` defaults. |
| `JWT_SECRET_KEY` | yes | — | HMAC secret used to sign access tokens. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never commit it. |
| `JWT_ALGORITHM` | no | `HS256` | JWT signing algorithm. |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | no | `60` | Token lifetime in minutes. |

Settings are loaded by `packages/shared/src/agentic_ecommerce_shared/config.py`,
which walks up from itself until it finds a `.env` at the repo root.
The location is fixed — the file must live at the repo root.

---

## Running the API

After first-time setup, the day-to-day loop is two commands:

```bash
docker compose up -d postgres        # no-op if already running
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

## Stopping the stack

```bash
# 1. Stop the API: Ctrl+C in the terminal running uvicorn.
# 2. Stop Postgres:
docker compose stop postgres         # pause (keeps container + data)
# or
docker compose down                  # remove container, keep data in volume
# or
docker compose down -v               # nuke everything including the volume
```

`docker compose down -v` is the right move when you change DB credentials
in `docker-compose.yml` — Postgres ignores new `POSTGRES_USER` /
`POSTGRES_PASSWORD` env vars if the data directory already exists.

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
| **`scaffold-resource`** | *"scaffold a new resource"*, *"create a new entity"*, *"add CRUD for X"*, *"generate endpoints for X"* | Orchestrates a multi-agent workflow that designs a new domain entity, designs its endpoints, then writes all files (model, migration, router, schemas, tests) and runs `pytest` + `ruff` before returning. **This is the required path for adding new domain resources** — it enforces the repo's pagination, auth, and audit-column conventions. |

Skill files live at `.claude/skills/<name>/SKILL.md`. Each skill can
have a `prompts/` subdirectory with specialist sub-agent briefs — see
`scaffold-resource/` for the pattern.

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
├── .env.example                   # copy to .env for local dev
├── CLAUDE.md                      # repo conventions for Claude
└── README.md
```

---

## Common commands

```bash
# Tests (no Postgres needed — uses in-memory SQLite)
uv run pytest -q                                  # full suite
uv run pytest apps/api/tests/test_auth.py -q      # one file
uv run pytest -k "test_login" -q                  # by name

# Lint + format
uv run ruff check .
uv run ruff format .

# Migrations (require Postgres up + .env configured)
cd apps/api
uv run alembic upgrade head         # apply all
uv run alembic downgrade -1         # roll back one
uv run alembic current              # show currently applied revision
uv run alembic history              # show all migrations
cd ../..

# User management
uv run agentic-ecommerce-create-user <username> <password> --role admin|seller|vendor|customer

# Local Postgres
docker compose up -d postgres
docker compose down -v              # stop + wipe all DB data
```

**Adding a new domain resource** — don't run `alembic revision` manually.
Use the `scaffold-resource` skill in Claude Code (see *Available skills*
above). It writes the model, migration, router, schemas, and tests in
one pass and leaves the repo green.

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

## End-to-end verification

A quick check that everything is wired up correctly, from a cold clone:

```bash
# 1. Cold-start the stack
uv sync
cp .env.example .env && echo "JWT_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" >> .env
docker compose up -d postgres
cd apps/api && uv run alembic upgrade head && cd ../..
uv run agentic-ecommerce-create-user alice s3cret --role admin

# 2. Tests pass (no DB needed)
uv run pytest -q

# 3. Lint + format clean
uv run ruff check . && uv run ruff format --check .

# 4. API boots
uv run agentic-ecommerce-api &
sleep 2
curl -sf http://127.0.0.1:8000/health
echo

# 5. Login works
curl -s -X POST http://127.0.0.1:8000/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"alice","password":"s3cret"}'
echo

# 6. Kill the API
kill %1
```

If all six steps succeed, the stack is healthy end-to-end.

---

## Deploying to a non-local environment

The local-dev story above is intentionally simple — Postgres in a
container, secrets in `.env`, HTTP over loopback. Before exposing this
API to anything but your laptop, change the following.

### TLS / HTTPS

The API binds to `127.0.0.1:8000` by design (see `main.py`'s `run()`).
Don't expose it directly to the internet — put a reverse proxy in front
that terminates TLS. Two common shapes:

**Caddy** (cheapest path; auto-issues Let's Encrypt certs):

```caddy
api.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

**nginx** (if you already run it):

```nginx
server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Cloudflare / Fly / Render / Railway / AWS ALB all work — the only
requirement is that JWTs never travel over plain HTTP.

### Secrets management

`.env` is fine for local-only. Never commit it, never bake it into a
Docker image, never copy it to a server. In production:

| Platform | Recommended source |
|---|---|
| AWS | Secrets Manager or Parameter Store (SecureString), injected as env vars by the task definition / runtime |
| GCP | Secret Manager, mounted via the Cloud Run / GKE secret integration |
| Fly.io | `fly secrets set JWT_SECRET_KEY=...` |
| Railway / Render | Their built-in env-var UI (encrypted at rest) |
| Kubernetes (self-hosted) | `Secret` resources + `envFrom`, or SOPS-encrypted manifests + a controller |
| Anywhere else | HashiCorp Vault with the agent injecting env at process start |

Required production env vars (same as `.env.example`):

- `DATABASE_URL` — points at your managed Postgres (RDS, Cloud SQL, Neon, Supabase, …).
- `JWT_SECRET_KEY` — at least 32 bytes, generated by
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Rotate
  on a schedule; rotation invalidates all outstanding tokens.

Rotation procedure (no-downtime):

1. Generate the new key.
2. Issue all new tokens with the new key (deploy with the new
   `JWT_SECRET_KEY`).
3. All sessions older than `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` are
   effectively invalidated; users re-auth.

### Rate limiter (production note)

The bundled `slowapi` limiter uses in-process memory. That's correct
for a single API process. **As soon as you run multiple replicas
behind a load balancer, switch to a shared backend** or per-IP limits
become per-replica limits:

```python
# Example: point slowapi at Redis. Set this via env in production.
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://prod-redis:6379",
)
```

We're not Redis-aware out of the box because no production target is
defined yet. When you pick one, wire `RATE_LIMIT_STORAGE_URI` (or
similar) into `Settings` and pass it through.

Behind a reverse proxy, also make sure slowapi sees the *real* client
IP rather than the proxy's loopback address. The proxy must set
`X-Forwarded-For` (the nginx config above does) and you'll want
slowapi's `get_remote_address` replaced with a helper that reads it.

### CI / dependency scanning

GitHub Actions runs `ruff check`, `ruff format --check`, and `pytest`
on every push + PR (`.github/workflows/ci.yml`).

Dependabot opens PRs weekly for:

- Python deps (grouped: routine minor/patch in one PR; CVEs separately).
- GitHub Action versions.

A `pip-audit` job runs in CI as a non-blocking advisory.

---

## Troubleshooting

- **`uv: command not found`** → PATH not set. See *Prerequisites*.
- **`password authentication failed for user "..."`** → your local `.env` doesn't match `docker-compose.yml`. Update `DATABASE_URL` to use the credentials in `.env.example`.
- **`relation "users" does not exist`** → migrations not applied. `cd apps/api && uv run alembic upgrade head`.
- **`ValidationError: JWT_SECRET_KEY required`** → `.env` doesn't exist or the key is empty. See step 2 of First-time setup.
- **Postgres won't accept new credentials after editing docker-compose** → existing volume keeps the old user. `docker compose down -v` then `docker compose up -d postgres`.
- **`address already in use` on port 5432** → another Postgres is already running on the host. Stop it (`brew services stop postgresql` or `sudo lsof -iTCP:5432 -sTCP:LISTEN`) or change the host port mapping in `docker-compose.yml`.
- **`address already in use` on port 8000** → kill the prior uvicorn process (`lsof -iTCP:8000 -sTCP:LISTEN`) or pass `--port` in a custom `uvicorn.run` call.
- **Docker container is `unhealthy`** → `docker compose logs postgres`. Most common cause is a partial volume from a prior failed run; `docker compose down -v` resets it.
