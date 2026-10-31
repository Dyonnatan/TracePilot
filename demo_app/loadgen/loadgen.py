"""Tráfego de base para o shop-api: dá às métricas um "normal" para
comparar com a anomalia. Sequência pseudoaleatória com seed fixa.
Nunca usa o cupom GRATIS100 (reservado ao cenário coupon_bug) nem o
produto 9 (esgotado).
"""
import os
import random
import time

import httpx

SHOP_URL = os.getenv("SHOP_URL", "http://localhost:8088")
REQUESTS_PER_SECOND = float(os.getenv("LOADGEN_RPS", "2"))
SEED = int(os.getenv("LOADGEN_SEED", "42"))
PRODUCT_IDS = list(range(1, 9))
SESSIONS = [f"loadgen-{index:02d}" for index in range(5)]
COUPONS = [None, None, None, "DESC10"]
PAYMENT_METHODS = ["pix", "card", "card", "boleto"]


def wait_for_shop(client: httpx.Client) -> None:
    while True:
        try:
            if client.get("/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        print("aguardando shop-api…", flush=True)
        time.sleep(2)


def random_cart(rng: random.Random) -> dict:
    # Quantidade 1 cabe no estoque dos produtos com estoque baixo.
    return {
        "items": [{"product_id": product_id, "quantity": 1} for product_id in rng.sample(PRODUCT_IDS, rng.randint(1, 3))],
        "coupon": rng.choice(COUPONS),
        "payment_method": rng.choice(PAYMENT_METHODS),
    }


def next_request(client: httpx.Client, rng: random.Random, headers: dict) -> httpx.Response:
    roll = rng.random()
    if roll < 0.50:
        return client.get("/products", headers=headers)
    if roll < 0.65:
        return client.get(f"/products/{rng.choice(PRODUCT_IDS)}", headers=headers)
    if roll < 0.75:
        return client.post("/cart/quote", headers=headers, json=random_cart(rng))
    return client.post("/checkout", headers=headers, json=random_cart(rng))


def main() -> None:
    rng = random.Random(SEED)
    client = httpx.Client(base_url=SHOP_URL, timeout=5, headers={"User-Agent": "tracepilot-loadgen/1.0"})
    wait_for_shop(client)

    stats: dict[str, int] = {}
    last_report = time.monotonic()
    interval = 1 / REQUESTS_PER_SECOND

    while True:
        headers = {"X-Session-Id": rng.choice(SESSIONS)}
        try:
            key = str(next_request(client, rng, headers).status_code)
        except httpx.HTTPError as exc:
            key = type(exc).__name__
        stats[key] = stats.get(key, 0) + 1

        if time.monotonic() - last_report >= 60:
            print(f"últimos 60s: {stats}", flush=True)
            stats.clear()
            last_report = time.monotonic()
        time.sleep(interval)


if __name__ == "__main__":
    main()
