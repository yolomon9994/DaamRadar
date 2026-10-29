"""Display-only rates from canonical pack contents; never select or rank offers."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

BASES = {"ml": (Decimal("1000"), "L"), "g": (Decimal("1000"), "kg"),
         "pc": (Decimal("1"), "item")}
PENNY = Decimal("0.01")


def standard_unit_price(product, price):
    """Return a PKR rate for the entire listed pack, or None for unusable data."""
    if product is None or product.unit not in BASES:
        return None
    try:
        quantity = Decimal(str(product.quantity))
        packs = Decimal(str(product.pack_count))
        price = Decimal(str(price))
    except (InvalidOperation, ValueError):
        return None
    if not all(value.is_finite() and value > 0 for value in (quantity, packs, price)):
        return None
    if packs != packs.to_integral_value() or (product.unit == "pc" and quantity != quantity.to_integral_value()):
        return None
    factor, unit = BASES[product.unit]
    amount = price * factor / (quantity * packs)
    rounded = amount.quantize(PENNY, rounding=ROUND_HALF_UP)
    if rounded == 0:
        # A positive observed price must never be presented as a free unit.
        return {"amount": None, "unit": unit, "less_than": "0.01", "display": f"< Rs. 0.01/{unit}"}
    return {"amount": format(rounded, ".2f"), "unit": unit, "less_than": None,
            "display": f"Rs. {rounded:,.2f}/{unit}"}
