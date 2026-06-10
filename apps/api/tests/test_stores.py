from __future__ import annotations

from agentic_ecommerce_api.db import Role, User
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# --- helpers -----------------------------------------------------------------


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _physical_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "physical",
        "name": "Downtown POS",
        "currency": "MXN",
        "timezone": "America/Mexico_City",
        "address_line1": "Av. Reforma 100",
        "city": "Ciudad de Mexico",
        "country": "mx",  # router uppercases
    }
    base.update(overrides)
    return base


def _online_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "online",
        "name": "Acme Brand Web",
        "currency": "USD",
        "timezone": "America/New_York",
        "domain": "shop.acme.example",
    }
    base.update(overrides)
    return base


def _marketplace_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "marketplace",
        "name": "Vince's Vintage",
        "currency": "USD",
        "timezone": "America/New_York",
    }
    base.update(overrides)
    return base


# --- creation: ADMIN can create any kind -------------------------------------


async def test_admin_creates_physical_store(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post("/stores", json=_physical_payload(), headers=_h(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "physical"
    assert body["slug"] == "downtown-pos"
    assert body["country"] == "MX"  # uppercased
    assert body["created_by"] == str(alice.id)


async def test_admin_creates_online_store(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post("/stores", json=_online_payload(), headers=_h(token))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "online"
    assert body["domain"] == "shop.acme.example"
    assert body["owner_user_id"] is None


async def test_admin_can_create_marketplace_for_another_user(
    client: AsyncClient, alice: User, vince: User
) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post(
        "/stores",
        json=_marketplace_payload(owner_user_id=str(vince.id)),
        headers=_h(token),
    )
    assert r.status_code == 201, r.text
    assert r.json()["owner_user_id"] == str(vince.id)


# --- creation: ONLINE / PHYSICAL gated to ADMIN ------------------------------


async def test_vendor_cannot_create_online(client: AsyncClient, vince: User) -> None:
    token = await _login(client, "vince", "vince-password")
    r = await client.post("/stores", json=_online_payload(), headers=_h(token))
    assert r.status_code == 403


async def test_customer_cannot_create_physical(client: AsyncClient, carol: User) -> None:
    token = await _login(client, "carol", "carol-password")
    r = await client.post("/stores", json=_physical_payload(), headers=_h(token))
    assert r.status_code == 403


async def test_seller_cannot_create_marketplace(client: AsyncClient, sam: User) -> None:
    token = await _login(client, "sam", "sam-password")
    r = await client.post("/stores", json=_marketplace_payload(), headers=_h(token))
    assert r.status_code == 403


# --- creation: kind-specific validation --------------------------------------


async def test_physical_requires_address(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post(
        "/stores",
        json=_physical_payload(city=None),
        headers=_h(token),
    )
    assert r.status_code == 422
    assert "city" in r.json()["detail"]


async def test_online_requires_domain(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post(
        "/stores",
        json=_online_payload(domain=None),
        headers=_h(token),
    )
    assert r.status_code == 422


async def test_online_rejects_owner(client: AsyncClient, alice: User, vince: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post(
        "/stores",
        json=_online_payload(owner_user_id=str(vince.id)),
        headers=_h(token),
    )
    assert r.status_code == 422


# --- creation: self-service vendor onboarding --------------------------------


async def test_customer_creating_marketplace_auto_promotes_to_vendor(
    client: AsyncClient, carol: User, db_session: AsyncSession
) -> None:
    token = await _login(client, "carol", "carol-password")
    r = await client.post("/stores", json=_marketplace_payload(), headers=_h(token))
    assert r.status_code == 201, r.text
    assert r.json()["owner_user_id"] == str(carol.id)

    # Carol is now a VENDOR in the DB.
    refreshed = (await db_session.execute(select(User).where(User.id == carol.id))).scalar_one()
    assert refreshed.role == Role.VENDOR


async def test_vendor_creates_own_marketplace(client: AsyncClient, vince: User) -> None:
    token = await _login(client, "vince", "vince-password")
    r = await client.post("/stores", json=_marketplace_payload(), headers=_h(token))
    assert r.status_code == 201
    assert r.json()["owner_user_id"] == str(vince.id)


async def test_vendor_owner_arg_is_ignored_uses_self(
    client: AsyncClient, vince: User, alice: User
) -> None:
    """A non-admin trying to set owner_user_id to someone else gets overridden
    to themselves — not a 403, since we silently strip the field."""
    token = await _login(client, "vince", "vince-password")
    r = await client.post(
        "/stores",
        json=_marketplace_payload(owner_user_id=str(alice.id)),
        headers=_h(token),
    )
    assert r.status_code == 201
    assert r.json()["owner_user_id"] == str(vince.id)


async def test_vendor_can_own_multiple_marketplaces(client: AsyncClient, vince: User) -> None:
    token = await _login(client, "vince", "vince-password")
    r1 = await client.post("/stores", json=_marketplace_payload(name="Shop One"), headers=_h(token))
    r2 = await client.post("/stores", json=_marketplace_payload(name="Shop Two"), headers=_h(token))
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["owner_user_id"] == r2.json()["owner_user_id"] == str(vince.id)


# --- creation: conflicts ----------------------------------------------------


async def test_duplicate_slug_returns_409(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _h(token)
    assert (await client.post("/stores", json=_physical_payload(), headers=h)).status_code == 201
    r = await client.post(
        "/stores",
        json=_physical_payload(address_line1="Different st."),
        headers=h,
    )
    assert r.status_code == 409


# --- read: anyone authenticated ---------------------------------------------


async def test_customer_can_list_stores(client: AsyncClient, alice: User, carol: User) -> None:
    admin_token = await _login(client, "alice", "correct-password")
    await client.post("/stores", json=_physical_payload(), headers=_h(admin_token))

    cust_token = await _login(client, "carol", "carol-password")
    r = await client.get("/stores", headers=_h(cust_token))
    assert r.status_code == 200
    assert r.json()["total"] == 1


async def test_list_filters_by_kind(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _h(token)
    await client.post("/stores", json=_physical_payload(), headers=h)
    await client.post("/stores", json=_online_payload(), headers=h)

    r = await client.get("/stores?kind=online", headers=h)
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["kind"] == "online"


# --- update: ADMIN any, VENDOR only own marketplace -------------------------


async def test_vendor_can_update_own_marketplace(client: AsyncClient, vince: User) -> None:
    token = await _login(client, "vince", "vince-password")
    created = (await client.post("/stores", json=_marketplace_payload(), headers=_h(token))).json()

    r = await client.patch(
        f"/stores/{created['id']}",
        json={"name": "Vince's Renamed Shop"},
        headers=_h(token),
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Vince's Renamed Shop"


async def test_vendor_cannot_update_another_vendors_store(
    client: AsyncClient, alice: User, vince: User, db_session: AsyncSession
) -> None:
    # Admin creates a marketplace owned by carol — but carol isn't loaded as
    # a fixture here; promote+create as vince, then have another vendor try.
    vince_token = await _login(client, "vince", "vince-password")
    created = (
        await client.post("/stores", json=_marketplace_payload(), headers=_h(vince_token))
    ).json()

    # Create a second vendor "wanda" inline.
    from agentic_ecommerce_api.auth import hash_password

    wanda = User(username="wanda", password_hash=hash_password("wanda-pw"), role=Role.VENDOR)
    db_session.add(wanda)
    await db_session.commit()

    wanda_token = await _login(client, "wanda", "wanda-pw")
    r = await client.patch(
        f"/stores/{created['id']}", json={"name": "hijack"}, headers=_h(wanda_token)
    )
    assert r.status_code == 403


async def test_vendor_cannot_update_physical_store(
    client: AsyncClient, alice: User, vince: User
) -> None:
    admin_token = await _login(client, "alice", "correct-password")
    created = (
        await client.post("/stores", json=_physical_payload(), headers=_h(admin_token))
    ).json()

    vince_token = await _login(client, "vince", "vince-password")
    r = await client.patch(f"/stores/{created['id']}", json={"name": "x"}, headers=_h(vince_token))
    assert r.status_code == 403


async def test_customer_cannot_update_store(client: AsyncClient, alice: User, carol: User) -> None:
    admin_token = await _login(client, "alice", "correct-password")
    created = (
        await client.post("/stores", json=_physical_payload(), headers=_h(admin_token))
    ).json()

    cust_token = await _login(client, "carol", "carol-password")
    r = await client.patch(f"/stores/{created['id']}", json={"name": "x"}, headers=_h(cust_token))
    assert r.status_code == 403


# --- delete -----------------------------------------------------------------


async def test_vendor_can_soft_delete_own_marketplace(client: AsyncClient, vince: User) -> None:
    token = await _login(client, "vince", "vince-password")
    created = (await client.post("/stores", json=_marketplace_payload(), headers=_h(token))).json()

    r = await client.delete(f"/stores/{created['id']}", headers=_h(token))
    assert r.status_code == 204

    r = await client.get(f"/stores/{created['id']}", headers=_h(token))
    assert r.status_code == 404


async def test_admin_can_delete_any_store(client: AsyncClient, alice: User, vince: User) -> None:
    vince_token = await _login(client, "vince", "vince-password")
    created = (
        await client.post("/stores", json=_marketplace_payload(), headers=_h(vince_token))
    ).json()

    admin_token = await _login(client, "alice", "correct-password")
    r = await client.delete(f"/stores/{created['id']}", headers=_h(admin_token))
    assert r.status_code == 204
