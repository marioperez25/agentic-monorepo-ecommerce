from fastapi import FastAPI

from agentic_ecommerce_api.routers import auth, health, inventory, products, storefront, stores

TAGS_METADATA = [
    {
        "name": "health",
        "description": "Liveness/readiness checks. Used by load balancers and uptime probes.",
    },
    {
        "name": "auth",
        "description": (
            "Authentication endpoints. Obtain a bearer token from "
            "`POST /auth/login`, then click **Authorize** in Swagger UI to "
            "attach it to subsequent requests."
        ),
    },
    {
        "name": "products",
        "description": (
            "Catalog CRUD. Stock and per-store availability are tracked separately (coming later)."
        ),
    },
    {
        "name": "stores",
        "description": (
            "Stores: physical POS locations, the platform's own online storefronts, and "
            "user-owned marketplace stores. Creating a marketplace store as a CUSTOMER "
            "auto-promotes you to VENDOR."
        ),
    },
    {
        "name": "inventory",
        "description": (
            "Stock per (store, product) pair plus an append-only movement audit log. "
            "Writes are ADMIN-only today; vendor self-service for marketplace stores "
            "will widen this later."
        ),
    },
    {
        "name": "storefront",
        "description": (
            "**Public, no authentication required.** Coarsened availability "
            "(`in_stock` / `low_stock` / `out_of_stock`) for ONLINE stores so "
            "guest visitors can see stock badges without a token. Exact "
            "quantities are never exposed here."
        ),
    },
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic Driven E-Commerce API",
        version="0.1.0",
        summary="REST API backing the agentic-ecommerce monorepo.",
        description=(
            "## Quickstart\n\n"
            "1. Create a user: `uv run agentic-ecommerce-create-user alice s3cret`\n"
            '2. POST `/auth/login` with `{ "username": "alice", "password": "s3cret" }`\n'
            "3. Copy the `access_token` from the response.\n"
            "4. Click **Authorize** above and paste the token.\n"
            "5. Protected routes (e.g. `GET /auth/me`) will now succeed.\n"
        ),
        contact={"name": "agentic-ecommerce maintainers"},
        license_info={"name": "MIT"},
        openapi_tags=TAGS_METADATA,
        swagger_ui_parameters={
            # Keep the pasted bearer token across page reloads — much less
            # painful when iterating in the docs UI.
            "persistAuthorization": True,
            "displayRequestDuration": True,
            "tryItOutEnabled": True,
        },
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(products.router)
    app.include_router(stores.router)
    app.include_router(inventory.router)
    app.include_router(storefront.router)
    return app


app = create_app()


def run() -> None:
    """Entry point used by the ``agentic-ecommerce-api`` console script."""
    import uvicorn

    uvicorn.run("agentic_ecommerce_api.main:app", host="127.0.0.1", port=8000, reload=False)
