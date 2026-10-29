from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.matching.normalization import identify
from catalog.models import Category, PriceHistory, Product, Retailer, RetailerListing
from catalog.services.observations import observation_context

CATEGORIES = [("Dairy & eggs", "dairy", "milk"), ("Pantry essentials", "pantry", "jar"),
              ("Snacks & treats", "snacks", "snack"), ("Drinks & tea", "drinks", "tea"),
              ("Household", "household", "cleaning"), ("Personal care", "personal-care", "care")]
# Deliberately invented examples. These are never represented as current retailer prices.
PRODUCTS = [
    ("olpers-milk-1l", "Olper's Full Cream Milk 1L", "Olper's", "dairy", "milk", [325, 340, 330]),
    ("nutella-350g", "Nutella Hazelnut Spread 350g", "Nutella", "pantry", "spread", [1450, 1520, 1495]),
    ("surf-excel-1kg", "Surf Excel Washing Powder 1kg", "Surf Excel", "household", "cleaning", [540, 565, 550]),
    ("national-ketchup-400g", "National Tomato Ketchup 400g", "National", "pantry", "sauce", [210, 225, 215]),
    ("lays-masala-70g", "Lay's Masala Chips 70g", "Lay's", "snacks", "snack", [100, 110, 105]),
    ("tapal-danedar-450g", "Tapal Danedar Tea 450g", "Tapal", "drinks", "tea", [920, 950, 935]),
    ("dalda-oil-1l", "Dalda Cooking Oil 1L", "Dalda", "pantry", "oil", [570, 595, 580]),
    ("shan-biryani-50g", "Shan Biryani Masala 50g", "Shan", "pantry", "spice", [140, 155, 145]),
    ("nestle-water-1500ml", "Nestle Pure Life Water 1.5L", "Nestle", "drinks", "water", [90, 100, 95]),
    ("lipton-yellow-label-190g", "Lipton Yellow Label Tea 190g", "Lipton", "drinks", "tea", [395, 420, 405]),
    ("olpers-milk-250ml", "Olper's Full Cream Milk 250ml", "Olper's", "dairy", "milk", [85, 90, 88]),
    ("lays-salted-70g", "Lay's Salted Chips 70g", "Lay's", "snacks", "snack", [100, 108, 105]),
]


class Command(BaseCommand):
    help = "Load explicitly labeled fictional demo data; safe to rerun, never modifies live records."

    @transaction.atomic
    def handle(self, *args, **options):
        call_command("seed_retailers", stdout=self.stdout)
        categories = {}
        for name, slug, icon in CATEGORIES:
            categories[slug], _ = Category.objects.get_or_create(slug=slug, defaults={"name": name, "icon": icon})
        retailers = [Retailer.objects.get(slug=s) for s in ["naheed", "springs", "alfatah"]]
        for slug, title, brand, category, illustration, prices in PRODUCTS:
            identity = identify(title, brand)
            if Product.objects.filter(slug=f"demo-{slug}", is_demo=False).exists():
                continue
            product, _ = Product.objects.update_or_create(slug=f"demo-{slug}", defaults={
                "canonical_name": title, "brand": brand, "category": categories[category],
                "quantity": identity.quantity, "unit": identity.unit, "variant": " ".join(sorted(identity.variants)),
                "illustration": illustration, "is_demo": True})
            if not product.is_demo:
                continue
            for retailer, price in zip(retailers, prices):
                listing, created = RetailerListing.objects.update_or_create(retailer=retailer, external_id=f"demo-{slug}", is_demo=True,
                    defaults={"product": product, "original_title": title, "current_price": Decimal(price),
                              "availability": "in_stock", "last_checked": timezone.now(), "delivery_area": "Demo area"})
                if created:
                    PriceHistory.objects.create(listing=listing, price=listing.current_price, checked_at=listing.last_checked,
                                                context=observation_context(listing, product=product, retailer=retailer))
        self.stdout.write(self.style.SUCCESS("Demo catalog ready: 12 sample products. Prices are fictional; no live prices were collected."))
