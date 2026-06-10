from __future__ import annotations

import pytest_asyncio
from agentic_ecommerce_api.auth import hash_password
from agentic_ecommerce_api.db import Role, User
from agentic_ecommerce_api.products import slugify
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# --- slug unit tests ---------------------------------------------------------


def test_slugify_basic() -> None:
    assert slugify("Cold Brew Concentrate") == "cold-brew-concentrate"


def test_slugify_collapses_punctuation() -> None:
    assert slugify("Hello,   World!!") == "hello-world"


def test_slugify_trims_leading_trailing() -> None:
    assert slugify("---wow---") == "wow"


def test_slugify_handles_unicode_by_dropping() -> None:
    # ASCII-only slugger; non-ASCII collapses to hyphens.
    assert slugify("café") == "caf"


# --- shared helpers ----------------------------------------------------------


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def bob(db_session: AsyncSession) -> User:
    """Second ADMIN — used to test creator-only logic among admins."""
    user = User(
        username="bob",
        password_hash=hash_password("bob-password"),
        role=Role.ADMIN,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Cold Brew Concentrate",
        "description": "32oz, makes 16 servings.",
        "price_cents": 1499,
        "currency": "usd",
        "sku": "CB-32-001",
    }
    base.update(overrides)
    return base


# --- POST /products ---------------------------------------------------------


async def test_create_product_succeeds_and_normalizes(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post("/products", json=_payload(), headers=_auth_headers(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Cold Brew Concentrate"
    assert body["slug"] == "cold-brew-concentrate"  # auto-generated
    assert body["currency"] == "USD"  # uppercased
    assert body["created_by"] == str(alice.id)
    assert body["is_active"] is True


async def test_create_product_requires_auth(client: AsyncClient) -> None:
    r = await client.post("/products", json=_payload())
    assert r.status_code == 401


async def test_create_product_rejects_duplicate_slug(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _auth_headers(token)
    r1 = await client.post("/products", json=_payload(sku=None), headers=h)
    assert r1.status_code == 201
    r2 = await client.post("/products", json=_payload(sku=None), headers=h)
    assert r2.status_code == 409


async def test_create_product_rejects_negative_price(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post(
        "/products",
        json=_payload(price_cents=-1),
        headers=_auth_headers(token),
    )
    assert r.status_code == 422


# --- GET /products (list) ---------------------------------------------------


async def test_list_products_paginates(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _auth_headers(token)
    for i in range(3):
        await client.post(
            "/products",
            json=_payload(name=f"Product {i}", sku=f"P-{i}"),
            headers=h,
        )

    r = await client.get("/products?page=1&limit=2", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["limit"] == 2
    assert body["total_pages"] == 2

    # page 2 returns the remaining item
    r2 = await client.get("/products?page=2&limit=2", headers=h)
    assert r2.status_code == 200
    body2 = r2.json()
    assert len(body2["items"]) == 1
    assert body2["page"] == 2


async def test_list_products_filters_with_q(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _auth_headers(token)
    await client.post("/products", json=_payload(name="Espresso", sku=None), headers=h)
    await client.post("/products", json=_payload(name="Tea Bag", sku="T-1"), headers=h)

    r = await client.get("/products?q=espresso", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Espresso"


async def test_list_excludes_soft_deleted_by_default(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _auth_headers(token)
    created = (await client.post("/products", json=_payload(), headers=h)).json()
    await client.delete(f"/products/{created['id']}", headers=h)

    r = await client.get("/products", headers=h)
    assert r.json()["total"] == 0

    r = await client.get("/products?include_inactive=true", headers=h)
    assert r.json()["total"] == 1


# --- GET /products/{id} -----------------------------------------------------


async def test_get_product_returns_404_when_missing(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.get(
        "/products/00000000-0000-0000-0000-000000000000",
        headers=_auth_headers(token),
    )
    assert r.status_code == 404


# --- PATCH /products/{id} ---------------------------------------------------


async def test_patch_product_updates_only_creator(
    client: AsyncClient, alice: User, bob: User
) -> None:
    alice_token = await _login(client, "alice", "correct-password")
    bob_token = await _login(client, "bob", "bob-password")
    created = (
        await client.post("/products", json=_payload(), headers=_auth_headers(alice_token))
    ).json()

    # Bob cannot edit Alice's product
    r = await client.patch(
        f"/products/{created['id']}",
        json={"price_cents": 999},
        headers=_auth_headers(bob_token),
    )
    assert r.status_code == 403

    # Alice can
    r = await client.patch(
        f"/products/{created['id']}",
        json={"price_cents": 999, "is_active": True},
        headers=_auth_headers(alice_token),
    )
    assert r.status_code == 200
    assert r.json()["price_cents"] == 999


# --- DELETE /products/{id} --------------------------------------------------


async def test_delete_product_is_soft_and_creator_only(
    client: AsyncClient, alice: User, bob: User
) -> None:
    alice_token = await _login(client, "alice", "correct-password")
    bob_token = await _login(client, "bob", "bob-password")
    created = (
        await client.post("/products", json=_payload(), headers=_auth_headers(alice_token))
    ).json()

    r = await client.delete(f"/products/{created['id']}", headers=_auth_headers(bob_token))
    assert r.status_code == 403

    r = await client.delete(f"/products/{created['id']}", headers=_auth_headers(alice_token))
    assert r.status_code == 204

    # GET after delete returns 404 (active-only by default)
    r = await client.get(f"/products/{created['id']}", headers=_auth_headers(alice_token))
    assert r.status_code == 404


# --- role gating ------------------------------------------------------------


async def test_customer_cannot_create_product(client: AsyncClient, carol: User) -> None:
    token = await _login(client, "carol", "carol-password")
    r = await client.post("/products", json=_payload(), headers=_auth_headers(token))
    assert r.status_code == 403


async def test_seller_cannot_create_product(client: AsyncClient, sam: User) -> None:
    token = await _login(client, "sam", "sam-password")
    r = await client.post("/products", json=_payload(), headers=_auth_headers(token))
    assert r.status_code == 403


async def test_customer_cannot_patch_or_delete_product(
    client: AsyncClient, alice: User, carol: User
) -> None:
    alice_token = await _login(client, "alice", "correct-password")
    carol_token = await _login(client, "carol", "carol-password")
    created = (
        await client.post("/products", json=_payload(), headers=_auth_headers(alice_token))
    ).json()

    r = await client.patch(
        f"/products/{created['id']}",
        json={"price_cents": 1},
        headers=_auth_headers(carol_token),
    )
    assert r.status_code == 403

    r = await client.delete(f"/products/{created['id']}", headers=_auth_headers(carol_token))
    assert r.status_code == 403


async def test_customer_can_read_products(client: AsyncClient, alice: User, carol: User) -> None:
    alice_token = await _login(client, "alice", "correct-password")
    await client.post("/products", json=_payload(), headers=_auth_headers(alice_token))

    carol_token = await _login(client, "carol", "carol-password")
    r = await client.get("/products", headers=_auth_headers(carol_token))
    assert r.status_code == 200
    assert r.json()["total"] == 1
