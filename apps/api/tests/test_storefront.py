"""Public storefront endpoints — guest access, coarsening, kind-gating."""

from __future__ import annotations

import pytest_asyncio
from agentic_ecommerce_api.db import User
from agentic_ecommerce_api.storefront import coarsen
from httpx import AsyncClient

# --- helpers -----------------------------------------------------------------


async def _login(client: AsyncClient, username: str, password: str) -> str:
    r = await client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
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


def _product_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Cold Brew Concentrate",
        "price_cents": 1499,
        "currency": "USD",
        "sku": "CB-32-001",
    }
    base.update(overrides)
    return base


@pytest_asyncio.fixture
async def public_setup(client: AsyncClient, alice: User) -> dict[str, str]:
    """One ONLINE store + one PHYSICAL store + three products with different
    stock levels at the ONLINE store: 200 (in stock), 3 (low, threshold 5),
    and 0 / no-row (out of stock)."""
    token = await _login(client, "alice", "correct-password")
    h = _h(token)

    online = (await client.post("/stores", json=_online_payload(), headers=h)).json()
    physical = (await client.post("/stores", json=_physical_payload(), headers=h)).json()

    in_stock = (
        await client.post(
            "/products",
            json=_product_payload(
                name="Plenty Brew",
                sku="PB-1",
                initial_inventory=[{"store_id": online["id"], "quantity": 200}],
            ),
            headers=h,
        )
    ).json()
    low_stock = (
        await client.post(
            "/products",
            json=_product_payload(
                name="Almost Out",
                sku="AO-1",
                initial_inventory=[
                    {"store_id": online["id"], "quantity": 3, "reorder_threshold": 5}
                ],
            ),
            headers=h,
        )
    ).json()
    no_row = (
        await client.post(
            "/products",
            json=_product_payload(name="Never Stocked", sku="NS-1"),
            headers=h,
        )
    ).json()

    return {
        "online_id": online["id"],
        "physical_id": physical["id"],
        "in_stock_id": in_stock["id"],
        "low_stock_id": low_stock["id"],
        "no_row_id": no_row["id"],
    }


# --- coarsen() unit tests ---------------------------------------------------


def test_coarsen_none_is_out() -> None:
    assert coarsen(None, None).value == "out_of_stock"


def test_coarsen_zero_is_out() -> None:
    assert coarsen(0, 10).value == "out_of_stock"


def test_coarsen_below_threshold_is_low() -> None:
    assert coarsen(3, 5).value == "low_stock"


def test_coarsen_at_threshold_is_low() -> None:
    assert coarsen(5, 5).value == "low_stock"


def test_coarsen_above_threshold_is_in_stock() -> None:
    assert coarsen(6, 5).value == "in_stock"


def test_coarsen_no_threshold_is_in_stock_when_positive() -> None:
    assert coarsen(1, None).value == "in_stock"


# --- single-pair: guest access (no token at all) ----------------------------


async def test_guest_can_read_single_in_stock(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    r = await client.get(
        f"/storefront/inventory/{public_setup['online_id']}/{public_setup['in_stock_id']}"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["availability"] == "in_stock"
    assert "quantity" not in body  # never leaked
    assert "reorder_threshold" not in body  # never leaked


async def test_guest_can_read_single_low_stock(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    r = await client.get(
        f"/storefront/inventory/{public_setup['online_id']}/{public_setup['low_stock_id']}"
    )
    assert r.json()["availability"] == "low_stock"


async def test_guest_single_no_row_is_out_of_stock(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    """A product with no inventory row at the storefront still returns 200
    with `out_of_stock`, not 404 — the product page should always render."""
    r = await client.get(
        f"/storefront/inventory/{public_setup['online_id']}/{public_setup['no_row_id']}"
    )
    assert r.status_code == 200
    assert r.json()["availability"] == "out_of_stock"


# --- single-pair: store-kind gating -----------------------------------------


async def test_physical_store_returns_404_for_guest(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    """PHYSICAL store ids must not be addressable on the public endpoint —
    same 404 shape as 'unknown id' so we don't confirm internal existence."""
    r = await client.get(
        f"/storefront/inventory/{public_setup['physical_id']}/{public_setup['in_stock_id']}"
    )
    assert r.status_code == 404


async def test_unknown_store_returns_404_for_guest(client: AsyncClient) -> None:
    r = await client.get(
        "/storefront/inventory/00000000-0000-0000-0000-000000000000/"
        "00000000-0000-0000-0000-000000000000"
    )
    assert r.status_code == 404


# --- batch: guest access ----------------------------------------------------


async def test_guest_batch_returns_coarsened_buckets(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    r = await client.post(
        "/storefront/inventory/lookup",
        json={
            "store_id": public_setup["online_id"],
            "product_ids": [
                public_setup["in_stock_id"],
                public_setup["low_stock_id"],
                public_setup["no_row_id"],
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["store_id"] == public_setup["online_id"]
    assert [item["availability"] for item in body["items"]] == [
        "in_stock",
        "low_stock",
        "out_of_stock",
    ]
    # Make sure none of the items leak quantity or threshold.
    for item in body["items"]:
        assert set(item.keys()) == {"product_id", "availability"}


async def test_guest_batch_preserves_order(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    ids = [
        public_setup["no_row_id"],
        public_setup["in_stock_id"],
        public_setup["low_stock_id"],
    ]
    r = await client.post(
        "/storefront/inventory/lookup",
        json={"store_id": public_setup["online_id"], "product_ids": ids},
    )
    assert [item["product_id"] for item in r.json()["items"]] == ids


async def test_guest_batch_physical_store_404(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    r = await client.post(
        "/storefront/inventory/lookup",
        json={
            "store_id": public_setup["physical_id"],
            "product_ids": [public_setup["in_stock_id"]],
        },
    )
    assert r.status_code == 404


async def test_guest_batch_rejects_empty_list(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    r = await client.post(
        "/storefront/inventory/lookup",
        json={"store_id": public_setup["online_id"], "product_ids": []},
    )
    assert r.status_code == 422


async def test_guest_batch_rejects_over_100_ids(
    client: AsyncClient, public_setup: dict[str, str]
) -> None:
    too_many = ["00000000-0000-0000-0000-000000000001"] * 101
    r = await client.post(
        "/storefront/inventory/lookup",
        json={"store_id": public_setup["online_id"], "product_ids": too_many},
    )
    assert r.status_code == 422
