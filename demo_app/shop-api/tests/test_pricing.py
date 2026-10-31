import pytest

import pricing


def test_quote_sums_lines_and_charges_shipping_below_threshold():
    assert pricing.quote([(12000, 2), (9900, 1)], 0, "card", "1.0.0") == {
        "subtotal_cents": 33900,
        "coupon_discount_cents": 0,
        "pix_discount_cents": 0,
        "shipping_cents": 2990,
        "total_cents": 36890,
    }


def test_free_shipping_from_threshold():
    quote = pricing.quote([(25000, 2)], 0, "card", "1.0.0")
    assert quote["shipping_cents"] == 0
    assert quote["total_cents"] == 50000


def test_pix_discount_applies_after_coupon_and_not_on_shipping():
    quote = pricing.quote([(10000, 1)], 10, "pix", "1.0.0")
    assert quote["coupon_discount_cents"] == 1000
    assert quote["pix_discount_cents"] == 450
    assert quote["total_cents"] == 10000 - 1000 - 450 + 2990


def test_full_discount_on_base_version_only_pays_shipping():
    quote = pricing.quote([(35000, 1)], 100, "card", "1.0.0")
    assert quote["total_cents"] == 2990
    assert "economia_cents" not in quote


def test_version_1_1_0_reports_savings():
    quote = pricing.quote([(10000, 1)], 10, "card", "1.1.0")
    assert quote["economia_cents"] == 1000


def test_version_1_1_0_breaks_with_full_discount():
    with pytest.raises(ZeroDivisionError):
        pricing.quote([(35000, 1)], 100, "card", "1.1.0")
