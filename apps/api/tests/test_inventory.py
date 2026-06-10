from __future__ import annotations

import pytest_asyncio
from agentic_ecommerce_api.auth import hash_password
from agentic_ecommerce_api.db import Role, User
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# --- helpers -----------------------------------------------------------------


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _product_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Cold Brew Concentrate",
        "description": "32oz, makes 16 servings.",
        "price_cents": 1499,
        "currency": "USD",
        "sku": "CB-32-001",
    }
    base.update(overrides)
    return base


def _physical_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "kind": "physical",
        "name": "Downtown POS",
        "currency": "MXN",
        "timezone": "America/Mexico_City",
        "address_line1": "Av. Reforma 100",
        "city": "Ciudad de Mexico",
        "country": "mx",
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


@pytest_asyncio.fixture
async def stocked(client: AsyncClient, alice: User) -> dict[str, str]:
    """Set up: 1 product, 2 stores (1 physical + 1 online), initial stock at
    both via the extended POST /products endpoint. Returns the ids."""
    token = await _login(client, "alice", "correct-password")
    h = _h(token)

    pos = (await client.post("/stores", json=_physical_payload(), headers=h)).json()
    web = (
        await client.post(
            "/stores",
            json=_online_payload(name="Brand A", domain="brand-a.example"),
            headers=h,
        )
    ).json()

    product = (
        await client.post(
            "/products",
            json=_product_payload(
                initial_inventory=[
                    {"store_id": pos["id"], "quantity": 50, "reorder_threshold": 10},
                    {"store_id": web["id"], "quantity": 200},
                ]
            ),
            headers=h,
        )
    ).json()

    return {
        "token": token,
        "product_id": product["id"],
        "pos_id": pos["id"],
        "web_id": web["id"],
    }


# --- POST /products initial_inventory ---------------------------------------


async def test_initial_inventory_creates_rows_and_movements(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, web_id, product_id = stocked["pos_id"], stocked["web_id"], stocked["product_id"]

    # Snapshot reads
    r1 = await client.get(f"/inventory/{pos_id}/{product_id}", headers=h)
    assert r1.status_code == 200
    assert r1.json()["quantity"] == 50
    assert r1.json()["reorder_threshold"] == 10

    r2 = await client.get(f"/inventory/{web_id}/{product_id}", headers=h)
    assert r2.json()["quantity"] == 200

    # Audit log has the 'initial' movements
    log = await client.get(f"/inventory/{pos_id}/{product_id}/movements", headers=h)
    assert log.status_code == 200
    body = log.json()
    assert body["total"] == 1
    assert body["items"][0]["reason"] == "initial"
    assert body["items"][0]["delta"] == 50
    assert body["items"][0]["quantity_after"] == 50


async def test_initial_inventory_rejects_unknown_store(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    r = await client.post(
        "/products",
        json=_product_payload(
            initial_inventory=[{"store_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}]
        ),
        headers=_h(token),
    )
    assert r.status_code == 422
    assert "unknown" in r.json()["detail"]


async def test_initial_inventory_rejects_duplicate_store(client: AsyncClient, alice: User) -> None:
    token = await _login(client, "alice", "correct-password")
    h = _h(token)
    pos = (await client.post("/stores", json=_physical_payload(), headers=h)).json()

    r = await client.post(
        "/products",
        json=_product_payload(
            initial_inventory=[
                {"store_id": pos["id"], "quantity": 5},
                {"store_id": pos["id"], "quantity": 7},
            ]
        ),
        headers=h,
    )
    assert r.status_code == 422
    assert "duplicate" in r.json()["detail"]


# --- single-pair read -------------------------------------------------------


async def test_get_inventory_row_404_when_missing(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    # different product_id never stocked
    r = await client.get(
        f"/inventory/{stocked['pos_id']}/00000000-0000-0000-0000-000000000000",
        headers=h,
    )
    assert r.status_code == 404


# --- PUT /inventory (set absolute) ------------------------------------------


async def test_put_inventory_writes_adjustment_movement(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.put(
        f"/inventory/{pos_id}/{product_id}",
        json={"quantity": 42, "note": "post-count adjust"},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["quantity"] == 42

    log = await client.get(f"/inventory/{pos_id}/{product_id}/movements", headers=h)
    items = log.json()["items"]
    assert items[0]["reason"] == "adjustment"
    assert items[0]["delta"] == 42 - 50  # -8
    assert items[0]["quantity_after"] == 42
    assert items[0]["note"] == "post-count adjust"


async def test_put_inventory_noop_does_not_log_movement(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.put(
        f"/inventory/{pos_id}/{product_id}",
        json={"quantity": 50},  # already 50
        headers=h,
    )
    assert r.status_code == 200

    log = await client.get(f"/inventory/{pos_id}/{product_id}/movements", headers=h)
    # Only the initial movement, no new adjustment.
    assert log.json()["total"] == 1


async def test_put_inventory_404_for_unknown_store(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    r = await client.put(
        f"/inventory/00000000-0000-0000-0000-000000000000/{stocked['product_id']}",
        json={"quantity": 1},
        headers=h,
    )
    assert r.status_code == 404


# --- POST /movements --------------------------------------------------------


async def test_post_movement_restock(client: AsyncClient, stocked: dict[str, str]) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": 25, "reason": "restock", "note": "delivery #88"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["delta"] == 25
    assert r.json()["quantity_after"] == 75

    snap = await client.get(f"/inventory/{pos_id}/{product_id}", headers=h)
    assert snap.json()["quantity"] == 75


async def test_post_movement_shrinkage_decrement(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": -3, "reason": "shrinkage"},
        headers=h,
    )
    assert r.status_code == 201
    assert r.json()["quantity_after"] == 47


async def test_post_movement_rejects_insufficient_stock(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": -9999, "reason": "sale"},
        headers=h,
    )
    assert r.status_code == 409


async def test_post_movement_rejects_zero_delta(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": 0, "reason": "adjustment"},
        headers=h,
    )
    assert r.status_code == 422


async def test_post_movement_rejects_invalid_reason(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": 1, "reason": "not-a-reason"},
        headers=h,
    )
    assert r.status_code == 422


# --- store-centric list ------------------------------------------------------


async def test_store_inventory_lists_with_product_info(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    r = await client.get(f"/stores/{stocked['pos_id']}/inventory", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["store"]["id"] == stocked["pos_id"]
    assert body["total"] == 1
    item = body["items"][0]
    assert item["product_id"] == stocked["product_id"]
    assert item["product_name"] == "Cold Brew Concentrate"
    assert item["product_sku"] == "CB-32-001"
    assert item["quantity"] == 50


async def test_store_inventory_low_stock_filter(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    # Drop stock to 5 (threshold is 10).
    await client.put(f"/inventory/{pos_id}/{product_id}", json={"quantity": 5}, headers=h)

    r = await client.get(f"/stores/{pos_id}/inventory?low_stock_only=true", headers=h)
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["quantity"] == 5

    # Web store had no threshold, so it shouldn't show up there.
    web_id = stocked["web_id"]
    r2 = await client.get(f"/stores/{web_id}/inventory?low_stock_only=true", headers=h)
    assert r2.json()["total"] == 0


# --- product-centric list ---------------------------------------------------


async def test_product_inventory_lists_with_store_info(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    r = await client.get(f"/products/{stocked['product_id']}/inventory", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["product"]["id"] == stocked["product_id"]
    assert body["total"] == 2
    kinds = {item["store_kind"] for item in body["items"]}
    assert kinds == {"physical", "online"}


# --- permission gating ------------------------------------------------------


async def test_customer_can_read_inventory(
    client: AsyncClient, stocked: dict[str, str], carol: User
) -> None:
    cust = _h(await _login(client, "carol", "carol-password"))
    r = await client.get(f"/inventory/{stocked['pos_id']}/{stocked['product_id']}", headers=cust)
    assert r.status_code == 200


async def test_customer_cannot_write_inventory(
    client: AsyncClient, stocked: dict[str, str], carol: User
) -> None:
    cust = _h(await _login(client, "carol", "carol-password"))

    r = await client.put(
        f"/inventory/{stocked['pos_id']}/{stocked['product_id']}",
        json={"quantity": 1},
        headers=cust,
    )
    assert r.status_code == 403

    r = await client.post(
        f"/inventory/{stocked['pos_id']}/{stocked['product_id']}/movements",
        json={"delta": 1, "reason": "restock"},
        headers=cust,
    )
    assert r.status_code == 403


# --- audit-log integrity ----------------------------------------------------


async def test_audit_log_orders_newest_first(
    client: AsyncClient, stocked: dict[str, str], db_session: AsyncSession
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": 10, "reason": "restock"},
        headers=h,
    )
    await client.post(
        f"/inventory/{pos_id}/{product_id}/movements",
        json={"delta": -5, "reason": "sale"},
        headers=h,
    )

    log = await client.get(f"/inventory/{pos_id}/{product_id}/movements", headers=h)
    items = log.json()["items"]
    assert len(items) == 3
    # Order: sale (newest), restock, initial
    assert [i["reason"] for i in items] == ["sale", "restock", "initial"]
    # Quantity-after audit
    assert [i["quantity_after"] for i in items] == [55, 60, 50]


# --- batch lookup -----------------------------------------------------------


async def test_lookup_returns_present_and_absent_products(
    client: AsyncClient, stocked: dict[str, str]
) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]
    unknown_id = "00000000-0000-0000-0000-000000000000"

    r = await client.post(
        "/inventory/lookup",
        json={"store_id": pos_id, "product_ids": [product_id, unknown_id]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["store_id"] == pos_id
    assert len(body["items"]) == 2

    by_pid = {it["product_id"]: it for it in body["items"]}
    assert by_pid[product_id]["quantity"] == 50
    assert by_pid[product_id]["present"] is True
    assert by_pid[unknown_id]["quantity"] == 0
    assert by_pid[unknown_id]["present"] is False


async def test_lookup_preserves_input_order(client: AsyncClient, stocked: dict[str, str]) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]
    other = "00000000-0000-0000-0000-000000000000"

    r = await client.post(
        "/inventory/lookup",
        json={"store_id": pos_id, "product_ids": [other, product_id]},
        headers=h,
    )
    assert [it["product_id"] for it in r.json()["items"]] == [other, product_id]


async def test_lookup_dedupes_repeated_ids(client: AsyncClient, stocked: dict[str, str]) -> None:
    h = _h(stocked["token"])
    pos_id, product_id = stocked["pos_id"], stocked["product_id"]

    r = await client.post(
        "/inventory/lookup",
        json={"store_id": pos_id, "product_ids": [product_id, product_id, product_id]},
        headers=h,
    )
    assert len(r.json()["items"]) == 1


async def test_lookup_rejects_unknown_store(client: AsyncClient, stocked: dict[str, str]) -> None:
    h = _h(stocked["token"])
    r = await client.post(
        "/inventory/lookup",
        json={
            "store_id": "00000000-0000-0000-0000-000000000000",
            "product_ids": [stocked["product_id"]],
        },
        headers=h,
    )
    assert r.status_code == 404


async def test_lookup_rejects_empty_list(client: AsyncClient, stocked: dict[str, str]) -> None:
    h = _h(stocked["token"])
    r = await client.post(
        "/inventory/lookup",
        json={"store_id": stocked["pos_id"], "product_ids": []},
        headers=h,
    )
    assert r.status_code == 422


async def test_lookup_rejects_over_100_ids(client: AsyncClient, stocked: dict[str, str]) -> None:
    h = _h(stocked["token"])
    too_many = ["00000000-0000-0000-0000-000000000001"] * 101
    r = await client.post(
        "/inventory/lookup",
        json={"store_id": stocked["pos_id"], "product_ids": too_many},
        headers=h,
    )
    assert r.status_code == 422


async def test_customer_can_lookup(
    client: AsyncClient, stocked: dict[str, str], carol: User
) -> None:
    cust = _h(await _login(client, "carol", "carol-password"))
    r = await client.post(
        "/inventory/lookup",
        json={"store_id": stocked["pos_id"], "product_ids": [stocked["product_id"]]},
        headers=cust,
    )
    assert r.status_code == 200


# Make pyright/ruff happy about the fixture imports.
_ = (User, AsyncSession, hash_password, Role)
