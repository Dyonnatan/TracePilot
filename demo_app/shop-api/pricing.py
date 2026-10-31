"""Cálculo de preço do carrinho e do checkout.

A versão 1.1.0 contém um bug proposital (cenário coupon_bug, gabarito em
demo_app/scenarios/coupon_bug.yaml). Não corrigir: o ambiente de
referência depende dele.
"""

SHIPPING_CENTS = 2990
FREE_SHIPPING_THRESHOLD_CENTS = 50000
PIX_DISCOUNT_PCT = 5


def parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def quote(lines: list[tuple[int, int]], discount_pct: int, payment_method: str, version: str) -> dict:
    """lines: [(unit_price_cents, quantity)]. O frete não recebe desconto."""
    subtotal_cents = sum(unit_price_cents * quantity for unit_price_cents, quantity in lines)
    desconto = discount_pct / 100
    coupon_discount_cents = round(subtotal_cents * desconto)
    total_com_cupom = subtotal_cents - coupon_discount_cents
    pix_discount_cents = round(total_com_cupom * PIX_DISCOUNT_PCT / 100) if payment_method == "pix" else 0
    shipping_cents = 0 if subtotal_cents >= FREE_SHIPPING_THRESHOLD_CENTS else SHIPPING_CENTS

    result = {
        "subtotal_cents": subtotal_cents,
        "coupon_discount_cents": coupon_discount_cents,
        "pix_discount_cents": pix_discount_cents,
        "shipping_cents": shipping_cents,
        "total_cents": total_com_cupom - pix_discount_cents + shipping_cents,
    }
    if parse_version(version) >= (1, 1, 0):
        result["economia_cents"] = calcular_economia(total_com_cupom, desconto)
    return result


def calcular_economia(total_cents: int, desconto: float) -> int:
    """Economia do cliente, reconstruída a partir do total já com desconto."""
    preco_original = total_cents / (1 - desconto)
    return round(preco_original - total_cents)
