import logging

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

import main

PRODUCTS = {
    1: {"id": 1, "name": "Teclado mecânico", "image": "/static/img/products/teclado.svg", "price_cents": 35000, "stock": 40},
    2: {"id": 2, "name": "Mouse sem fio", "image": "/static/img/products/mouse.svg", "price_cents": 12000, "stock": 3},
    9: {"id": 9, "name": "Cabo USB-C", "image": "/static/img/products/cabo.svg", "price_cents": 9900, "stock": 0},
}
COUPONS = {"DESC10": {"code": "DESC10", "discount_pct": 10}, "GRATIS100": {"code": "GRATIS100", "discount_pct": 100}}


def cart(*items, coupon=None, payment_method="card"):
    return {
        "items": [{"product_id": product_id, "quantity": quantity} for product_id, quantity in items],
        "coupon": coupon,
        "payment_method": payment_method,
    }


@pytest.fixture
def orders(monkeypatch):
    created = []
    monkeypatch.setattr(main.db, "list_products", lambda: list(PRODUCTS.values()))
    monkeypatch.setattr(main.db, "get_product", PRODUCTS.get)
    monkeypatch.setattr(
        main.db, "get_last_purchase", lambda session_id, product_id: "2026-10-12T10:00:00+00:00" if session_id == "s-1" else None
    )
    monkeypatch.setattr(
        main.db, "get_products", lambda ids: {pid: PRODUCTS[pid] for pid in ids if pid in PRODUCTS}
    )
    monkeypatch.setattr(main.db, "get_coupon", COUPONS.get)
    monkeypatch.setattr(main.db, "create_order", lambda *args: created.append(args) or len(created))
    monkeypatch.setattr(
        main.payment_client, "authorize", lambda order_ref, amount_cents: {"authorization_id": "AUTH-TEST"}
    )
    return created


@pytest.fixture
def client():
    return TestClient(main.app, raise_server_exceptions=False)


def test_products(client, orders):
    response = client.get("/products")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_product_detail(client, orders):
    body = client.get("/products/1").json()
    assert (body["name"], body["purchased_at"]) == ("Teclado mecânico", None)
    assert client.get("/products/1", headers={"X-Session-Id": "s-1"}).json()["purchased_at"].startswith("2026-10-12")
    assert client.get("/products/99").status_code == 404


def test_cart_quote(client, orders):
    response = client.post("/cart/quote", json=cart((1, 1), (2, 2), coupon="desc10", payment_method="pix"))
    assert response.status_code == 200
    body = response.json()
    assert body["subtotal_cents"] == 59000
    assert body["coupon"] == "DESC10"
    assert body["coupon_discount_cents"] == 5900
    assert body["pix_discount_cents"] == 2655
    assert body["shipping_cents"] == 0
    assert body["items"][1]["line_total_cents"] == 24000
    assert orders == []


def test_cart_quote_unknown_coupon_points_to_field(client, orders):
    response = client.post("/cart/quote", json=cart((1, 1), coupon="NOPE"))
    assert response.status_code == 422
    assert response.json() == {"detail": "cupom inválido", "field": "coupon"}


def test_cart_rejects_sold_out_and_insufficient_stock(client, orders):
    assert client.post("/cart/quote", json=cart((9, 1))).status_code == 409
    assert client.post("/cart/quote", json=cart((2, 4))).status_code == 409


def test_cart_rejects_duplicate_products(client, orders):
    assert client.post("/cart/quote", json=cart((1, 1), (1, 2))).status_code == 422


def test_checkout_success(client, orders):
    response = client.post(
        "/checkout", json=cart((1, 2), coupon="desc10", payment_method="boleto"), headers={"X-Session-Id": "s-1"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == 1
    assert body["total_cents"] == 63000
    lines, coupon, payment_method, totals, session_id, authorization_id = orders[0]
    assert [(line["product_id"], line["quantity"]) for line in lines] == [(1, 2)]
    assert (coupon, payment_method, session_id, authorization_id) == ("DESC10", "boleto", "s-1", "AUTH-TEST")
    assert totals["total_cents"] == 63000


def test_checkout_rejects_zero_quantity(client, orders):
    assert client.post("/checkout", json=cart((1, 0))).status_code == 422


def test_checkout_rejects_empty_cart(client, orders):
    assert client.post("/checkout", json=cart()).status_code == 422


def test_checkout_unknown_product(client, orders):
    assert client.post("/checkout", json=cart((99, 1))).status_code == 404


def test_full_discount_works_on_base_version(client, orders, monkeypatch):
    monkeypatch.setattr(main, "SHOP_VERSION", "1.0.0")
    response = client.post("/checkout", json=cart((1, 1), coupon="GRATIS100"))
    assert response.status_code == 200
    assert response.json()["total_cents"] == 2990


def test_coupon_bug_only_on_1_1_0(client, orders, monkeypatch):
    monkeypatch.setattr(main, "SHOP_VERSION", "1.1.0")
    for path in ("/cart/quote", "/checkout"):
        response = client.post(path, json=cart((1, 1), coupon="GRATIS100"))
        assert response.status_code == 500
        assert response.json()["detail"] == "erro interno"
        assert "trace_id" in response.json()

    response = client.post("/cart/quote", json=cart((1, 1), coupon="DESC10"))
    assert response.status_code == 200
    assert response.json()["economia_cents"] == 3500


def test_payment_timeout_returns_504(client, orders, monkeypatch):
    def timeout(order_ref, amount_cents):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(main.payment_client, "authorize", timeout)
    response = client.post("/checkout", json=cart((1, 1)))
    assert response.status_code == 504
    assert response.json()["detail"] == "pagamento indisponível"


def test_payment_5xx_returns_502(client, orders, monkeypatch, caplog):
    def upstream_error(order_ref, amount_cents):
        request = httpx.Request("POST", "http://payment/authorize")
        raise httpx.HTTPStatusError("503", request=request, response=httpx.Response(503, request=request))

    monkeypatch.setattr(main.payment_client, "authorize", upstream_error)
    response = client.post("/checkout", json=cart((1, 1)))
    assert response.status_code == 502
    assert response.json()["detail"] == "pagamento indisponível"
    record = next(r for r in caplog.records if getattr(r, "event_type", None) == "payment.error")
    assert getattr(record, "payment.upstream_status") == 503


def test_n_plus_one_flag_queries_one_product_at_a_time(client, orders, monkeypatch):
    calls = []
    monkeypatch.setattr(main.db, "list_products_one_by_one", lambda: calls.append("list") or list(PRODUCTS.values()))
    monkeypatch.setattr(
        main.db,
        "get_products_one_by_one",
        lambda ids: calls.append("get") or {pid: PRODUCTS[pid] for pid in ids if pid in PRODUCTS},
    )
    assert client.get("/products").status_code == 200
    assert client.post("/cart/quote", json=cart((1, 1))).status_code == 200
    assert calls == []

    main.faults.registry.set(main.faults.CATALOG_N_PLUS_ONE, True)
    assert len(client.get("/products").json()) == 3
    assert client.post("/cart/quote", json=cart((1, 1))).status_code == 200
    assert calls == ["list", "get"]


def test_unbounded_cache_grows_and_clears_on_disable(client, orders):
    main.faults.registry.set(main.faults.PRODUCT_CACHE_UNBOUNDED, True, {"kb_per_request": 1})
    for _ in range(3):
        client.get("/products/1")
    client.get("/products")
    assert len(main.product_render_cache) == 4
    assert all(len(value) == 1024 for value in main.product_render_cache.values())

    main.faults.registry.set(main.faults.PRODUCT_CACHE_UNBOUNDED, False)
    assert main.product_render_cache == {}


def test_blocking_audit_sleeps_inside_request(client, orders, monkeypatch):
    sleeps = []
    monkeypatch.setattr(main.time, "sleep", sleeps.append)
    client.get("/products")
    assert sleeps == []

    main.faults.registry.set(main.faults.AUDIT_SYNC_WRITE, True, {"sleep_ms": 150})
    client.get("/products")
    client.get("/health")
    assert sleeps == [0.15]


def test_chatty_logging_emits_debug_payload_lines(client, orders, caplog):
    caplog.set_level(logging.INFO, logger="shop")
    main.faults.registry.set(main.faults.DEBUG_PAYLOAD_LOGGING, True, {"lines": 5})
    client.get("/products")
    debug_lines = [r for r in caplog.records if getattr(r, "event_type", None) == "debug.payload"]
    assert len(debug_lines) == 5


def test_flag_change_logs_change_event(caplog):
    caplog.set_level(logging.INFO, logger="shop")
    main.faults.registry.set(main.faults.CATALOG_N_PLUS_ONE, True)
    main.faults.registry.set(main.faults.CATALOG_N_PLUS_ONE, True)
    changes = [r for r in caplog.records if getattr(r, "event_type", None) == "change.event"]
    assert len(changes) == 1
    assert getattr(changes[0], "change.type") == "feature_flag"
    assert getattr(changes[0], "change.flag") == "catalog_n_plus_one"


def test_db_lock_returns_503(client, orders, monkeypatch):
    def locked(*_args):
        raise psycopg.errors.QueryCanceled("canceling statement due to statement timeout")

    monkeypatch.setattr(main.db, "get_products", locked)
    monkeypatch.setattr(main.db, "list_products", locked)
    assert client.post("/checkout", json=cart((1, 1))).status_code == 503
    assert client.post("/cart/quote", json=cart((1, 1))).status_code == 503
    assert client.get("/products").status_code == 503


def test_rum_event(client):
    response = client.post(
        "/rum/events", json={"session_id": "s-1", "type": "checkout_attempt", "detail": {"product_id": 1}}
    )
    assert response.status_code == 202


def test_rum_event_rejects_nested_detail(client):
    response = client.post("/rum/events", json={"session_id": "s-1", "type": "x", "detail": {"a": {"b": 1}}})
    assert response.status_code == 422


def test_support_report_returns_ticket(client):
    response = client.post(
        "/support/report", json={"session_id": "s-1", "message": "não consegui concluir", "trace_id": "a" * 32}
    )
    assert response.status_code == 201
    assert response.json()["ticket"].startswith("TP-")


def test_support_report_rejects_invalid_trace_id(client):
    response = client.post("/support/report", json={"session_id": "s-1", "message": "x", "trace_id": "<script>"})
    assert response.status_code == 422
