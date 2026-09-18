from decimal import Decimal

from django.conf import settings

from .models import DeliveryZone


def resolve_zone(address):
    """Find the best-matching active DeliveryZone for a DeliveryAddress.

    Matches by case-insensitive substring against the address's `area`
    field. Returns None if no zone matches (caller should fall back to the
    default flat DELIVERY_FEE) or if the matched zone is inactive
    (deliveries currently unavailable there).
    """
    if not address:
        return None
    area = (address.area or '').strip().lower()
    if not area:
        return None
    for zone in DeliveryZone.objects.all():
        if zone.name.strip().lower() in area or area in zone.name.strip().lower():
            return zone
    return None


def get_delivery_fee(address, cart_subtotal=None):
    """Return (fee, zone_or_None, is_deliverable).

    Free delivery applies at both ends of the order-size spectrum:
    small orders (<= FREE_DELIVERY_MAX_SMALL_ORDER, a low-fuss threshold)
    and bulk/wholesale orders (>= FREE_DELIVERY_MIN_WHOLESALE_ORDER).
    Everything in between pays the normal zone-based fee.
    """
    zone = resolve_zone(address)

    if zone is not None and not zone.is_active:
        return None, zone, False

    free_small = settings.FREE_DELIVERY_MAX_SMALL_ORDER
    free_bulk = settings.FREE_DELIVERY_MIN_WHOLESALE_ORDER
    if cart_subtotal is not None and (
        (free_small > 0 and cart_subtotal <= free_small)
        or (free_bulk > 0 and cart_subtotal >= free_bulk)
    ):
        return Decimal('0.00'), zone, True

    if zone is None:
        return settings.DELIVERY_FEE, None, True
    return zone.delivery_fee, zone, True
