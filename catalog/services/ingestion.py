"""All imports go through one atomic boundary, including history snapshots."""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from catalog.matching.normalization import identify, match_score
from catalog.models import PriceHistory, Product, RetailerListing
from catalog.services.observations import observation_context


@transaction.atomic
def ingest(retailer, item, *, is_demo=False, category=None, illustration=None, create_only=False):
    try:
        price = Decimal(str(item.price))
        if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -2 or price >= Decimal("10000000000"):
            raise ValueError()
    except (InvalidOperation, ValueError):
        raise ValidationError("A positive PKR amount with at most two decimals is required.")
    if item.currency != "PKR":
        raise ValidationError("Only explicitly denominated PKR prices are accepted.")
    parsed_url, retailer_url = urlparse(item.url), urlparse(retailer.website)
    if not is_demo and (parsed_url.scheme != "https" or parsed_url.netloc != retailer_url.netloc or parsed_url.username):
        raise ValidationError("Product URL must belong to the retailer's HTTPS origin.")
    if not item.title or not item.external_id:
        raise ValidationError("Title and retailer product identifier are required.")
    if item.availability not in RetailerListing.Availability.values:
        raise ValidationError("Invalid availability.")
    if create_only:
        preserved = RetailerListing.objects.select_for_update().filter(retailer=retailer, is_demo=is_demo).filter(
            Q(url=item.url) | Q(external_id=item.external_id)).first()
        if preserved:
            return preserved, False
    identity = identify(item.title, item.brand, item.gtin)
    existing = RetailerListing.objects.select_for_update().filter(retailer=retailer, external_id=item.external_id,
                 delivery_area=item.delivery_area, is_demo=is_demo).select_related("product").first()
    product = None
    if existing:
        previous_identity = identify(existing.product.canonical_name, existing.product.brand, existing.product.gtin)
        if identity == previous_identity or match_score(identity, previous_identity) >= 92:
            product = existing.product
    if product is None and identity.quantity is not None and identity.brand:
        candidates = Product.objects.filter(is_demo=is_demo, quantity=identity.quantity, unit=identity.unit, pack_count=identity.pack_count)
        scored = sorted([(match_score(identity, identify(p.canonical_name, p.brand, p.gtin)), p) for p in candidates], key=lambda entry: entry[0], reverse=True)
        if scored and scored[0][0] >= 92 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 5):
            product = scored[0][1]
    if product is None:
        # Unknown and ambiguous products remain separate; never silently merge them.
        product = Product.objects.create(canonical_name=item.title[:255], slug=f"{slugify(item.title)[:220]}-{uuid4().hex[:10]}",
            brand=identity.brand, quantity=identity.quantity, unit=identity.unit, pack_count=max(1, identity.pack_count),
            variant=" ".join(sorted(identity.variants)), packaging=" ".join(sorted(identity.packaging)),
            gtin=identity.gtin, image=item.image, category=category, is_demo=is_demo,
            illustration=illustration or ("milk" if {"milk", "milkpak"} & set(identity.name.split()) else "basket"))
    checked_at = timezone.now()
    save_listing = RetailerListing.objects.get_or_create if create_only else RetailerListing.objects.update_or_create
    listing, created = save_listing(retailer=retailer, external_id=item.external_id,
        delivery_area=item.delivery_area, is_demo=is_demo, defaults={"product": product, "original_title": item.title,
        "url": item.url, "current_price": price, "currency": "PKR", "availability": item.availability, "last_checked": checked_at,
        # Current adapters have no verified location context. Evidence for an earlier check cannot carry forward.
        "delivery_area_key": "", "area_evidence_url": "", "area_verified_at": None})
    if create_only and not created:
        # A competing insert won the unique-key race. Undo any new canonical product.
        transaction.set_rollback(True)
        return listing, False
    PriceHistory.objects.create(listing=listing, price=price, checked_at=checked_at,
                                context=observation_context(listing, product=product, retailer=retailer))
    return listing, created
