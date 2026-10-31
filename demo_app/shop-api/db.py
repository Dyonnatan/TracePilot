"""Acesso ao Postgres. Uma conexão por operação, com statement_timeout
curto para que um lock na tabela vire erro em vez de travar o request.
"""
import os
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://shop:shop@localhost:5432/shop")
STATEMENT_TIMEOUT_MS = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "2000"))

PRODUCT_COLUMNS = (
    "id, slug, name, category, description, specs, image, price_cents, stock, rating::float AS rating, reviews_count"
)


def _connect() -> psycopg.Connection:
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=3,
        application_name="shop-api",
        options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
    )


def list_products() -> list[dict]:
    with _connect() as conn:
        return conn.execute(f"SELECT {PRODUCT_COLUMNS} FROM products ORDER BY id").fetchall()


def get_product(product_id: int) -> dict | None:
    with _connect() as conn:
        return conn.execute(f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = %s", (product_id,)).fetchone()


def get_last_purchase(session_id: str, product_id: int) -> datetime | None:
    """Última compra do produto pela sessão; depende de orders_session_id_idx."""
    with _connect() as conn:
        return conn.execute(
            """
            SELECT max(o.created_at) AS purchased_at
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            WHERE o.session_id = %s AND oi.product_id = %s
            """,
            (session_id, product_id),
        ).fetchone()["purchased_at"]


def get_products(product_ids: list[int]) -> dict[int, dict]:
    with _connect() as conn:
        rows = conn.execute(f"SELECT {PRODUCT_COLUMNS} FROM products WHERE id = ANY(%s)", (product_ids,)).fetchall()
    return {row["id"]: row for row in rows}


def list_products_one_by_one() -> list[dict]:
    """Anti-pattern N+1 (flag catalog_n_plus_one): busca os ids e depois faz
    uma consulta, com conexão nova, por produto."""
    with _connect() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM products ORDER BY id").fetchall()]
    return [found for product_id in ids if (found := get_product(product_id)) is not None]


def get_products_one_by_one(product_ids: list[int]) -> dict[int, dict]:
    """Versão N+1 de get_products (flag catalog_n_plus_one)."""
    return {product_id: found for product_id in product_ids if (found := get_product(product_id)) is not None}


def get_coupon(code: str) -> dict | None:
    with _connect() as conn:
        return conn.execute("SELECT code, discount_pct FROM coupons WHERE code = %s", (code,)).fetchone()


def create_order(
    items: list[dict],
    coupon: str | None,
    payment_method: str,
    totals: dict,
    session_id: str | None,
    authorization_id: str | None,
) -> int:
    """items: [{"product_id", "quantity", "unit_price_cents"}]; totals vem de pricing.quote."""
    with _connect() as conn, conn.transaction():
        order_id = conn.execute(
            """
            INSERT INTO orders (coupon, payment_method, subtotal_cents, shipping_cents, discount_cents,
                                total_cents, session_id, authorization_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                coupon,
                payment_method,
                totals["subtotal_cents"],
                totals["shipping_cents"],
                totals["coupon_discount_cents"] + totals["pix_discount_cents"],
                totals["total_cents"],
                session_id,
                authorization_id,
            ),
        ).fetchone()["id"]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) VALUES (%s, %s, %s, %s)",
                [(order_id, item["product_id"], item["quantity"], item["unit_price_cents"]) for item in items],
            )
        return order_id
