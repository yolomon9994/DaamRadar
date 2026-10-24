"""Synthetic delivery evidence exercises comparison rules, not retailer coverage."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.utils import timezone

from catalog.admin import ListingAdmin
from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.scraping.types import ScrapedProduct
from catalog.services.catalog import decorate, get_product_queryset
from catalog.services.ingestion import ingest


class DeliveryAreaTests(TestCase):
    def setUp(self):
        self.checked = timezone.now() - timedelta(minutes=5)
        self.verified = timezone.now() - timedelta(minutes=1)
        self.product = Product.objects.create(canonical_name="Synthetic Milk 1L", slug="synthetic-milk", quantity=1000, unit="ml")
        self.retailers = [Retailer.objects.create(name=f"Test retailer {i}", slug=f"test-{i}", website=f"https://retailer-{i}.example") for i in range(3)]
        self.offers = [RetailerListing.objects.create(product=self.product, retailer=retailer, external_id="milk-1", original_title="Synthetic Milk 1L",
            url=f"{retailer.website}/milk", current_price=Decimal(100 + i * 10), availability="in_stock", last_checked=self.checked,
            delivery_area="Test district") for i, retailer in enumerate(self.retailers[:2])]

    def verify(self, offer, **changes):
        offer.delivery_area_key = "pk-test-district"
        offer.area_evidence_url = offer.retailer.website + "/public-area-offer"
        offer.area_verified_at = self.verified
        for key, value in changes.items():
            setattr(offer, key, value)
        offer.full_clean()
        offer.save()

    def decorated(self):
        return decorate(get_product_queryset().get(pk=self.product.pk))

    def test_same_area_text_alone_never_establishes_verification(self):
        product = self.decorated()
        self.assertFalse(product.has_mixed_areas)
        self.assertTrue(product.has_unverified_areas)
        self.assertFalse(product.has_comparison)
        self.assertFalse(product.best_ids)
        self.assertEqual(product.best_price, Decimal(100))
        self.assertEqual(product.savings, 0)

    def test_same_verified_scope_enables_winner_and_spread(self):
        for offer in self.offers:
            self.verify(offer)
        product = self.decorated()
        self.assertTrue(product.has_comparison)
        self.assertFalse(product.has_unverified_areas)
        self.assertEqual(product.best_ids, {self.offers[0].pk})
        self.assertEqual(product.savings, 10)
        self.assertEqual(product.comparison_area, "Test district")
        self.offers[1].current_price = 100
        self.offers[1].save()
        self.assertEqual(self.decorated().best_ids, {offer.pk for offer in self.offers})

    def test_distinct_scope_keys_prevent_winner_despite_same_labels(self):
        self.verify(self.offers[0])
        self.verify(self.offers[1], delivery_area_key="pk-other-district")
        product = self.decorated()
        self.assertTrue(product.has_mixed_areas)
        self.assertFalse(product.has_comparison)
        self.assertFalse(product.best_ids)
        self.assertEqual(product.savings, 0)

    def test_shared_scope_key_accepts_different_display_labels(self):
        self.verify(self.offers[0])
        self.verify(self.offers[1], delivery_area="Test district, Pakistan")
        self.assertTrue(self.decorated().has_comparison)
        self.assertFalse(self.decorated().has_mixed_areas)

    def test_unverified_eligible_offer_prevents_comparison(self):
        self.verify(self.offers[0])
        self.assertFalse(self.decorated().has_comparison)
        self.verify(self.offers[1])
        RetailerListing.objects.create(product=self.product, retailer=self.retailers[2], external_id="milk-1", original_title="Synthetic Milk 1L",
            url=self.retailers[2].website + "/milk", current_price=50, availability="in_stock", last_checked=self.checked,
            delivery_area="Test district")
        product = self.decorated()
        self.assertEqual(product.best_price, 50)
        self.assertFalse(product.best_ids)

    def test_only_fresh_in_stock_verified_offers_can_win(self):
        for offer in self.offers:
            self.verify(offer)
        third = RetailerListing.objects.create(product=self.product, retailer=self.retailers[2], external_id="milk-1", original_title="Synthetic Milk 1L",
            url=self.retailers[2].website + "/milk", current_price=50, availability="out_of_stock", last_checked=self.checked)
        for availability in ("out_of_stock", "unknown", "in_stock"):
            third.availability = availability
            third.last_checked = self.checked - timedelta(days=3) if availability == "in_stock" else self.checked
            third.save()
            product = self.decorated()
            self.assertTrue(product.has_comparison)
            self.assertEqual(product.best_price, 100)
            self.assertEqual(product.best_ids, {self.offers[0].pk})
            response = self.client.get("/products/synthetic-milk/")
            self.assertContains(response, "Lowest fresh in-stock listed price")
            self.assertContains(response, "Compared for Test district")
        self.offers[0].last_checked = self.checked - timedelta(days=3)
        self.offers[0].save()
        self.assertFalse(self.decorated().has_comparison)

    def test_one_retailer_with_multiple_verified_listings_cannot_win(self):
        for offer in self.offers:
            self.verify(offer)
        self.offers[1].retailer = self.retailers[0]
        self.offers[1].external_id = "second-milk-record"
        self.offers[1].area_evidence_url = self.retailers[0].website + "/public-area-offer"
        self.offers[1].save()
        self.assertFalse(self.decorated().has_comparison)

    def test_invalid_or_incomplete_evidence_is_rejected(self):
        offer = self.offers[0]
        valid = {"delivery_area": "Test district", "delivery_area_key": "pk-test-district",
                 "area_evidence_url": offer.retailer.website + "/public-area-offer", "area_verified_at": self.verified,
                 "is_demo": False}
        changes = [{"delivery_area": ""}, {"delivery_area": "Area unverified"}, {"delivery_area": "Unknown"},
                   {"delivery_area_key": ""}, {"delivery_area_key": "BAD_SCOPE"}, {"area_evidence_url": ""},
                   {"area_evidence_url": "http://retailer-0.example/evidence"}, {"area_evidence_url": "https://other.example/evidence"},
                   {"area_evidence_url": "https://user@retailer-0.example/evidence"},
                   {"area_evidence_url": offer.retailer.website + "/evidence#section"},
                   {"area_verified_at": None}, {"area_verified_at": self.checked - timedelta(seconds=1)},
                   {"area_verified_at": timezone.now() + timedelta(hours=1)}, {"is_demo": True}]
        for change in changes:
            for key, value in {**valid, **change}.items():
                setattr(offer, key, value)
            with self.subTest(change=change):
                self.assertFalse(offer.area_is_verified)
                with self.assertRaises(ValidationError):
                    offer.full_clean()

    def test_database_rejects_partial_proof(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RetailerListing.objects.filter(pk=self.offers[0].pk).update(delivery_area_key="pk-test-district")

    def test_verification_for_an_older_check_does_not_carry_forward(self):
        for offer in self.offers:
            self.verify(offer)
        RetailerListing.objects.filter(pk=self.offers[0].pk).update(last_checked=timezone.now())
        self.assertFalse(self.decorated().has_comparison)
        self.assertFalse(self.client.get("/api/products/synthetic-milk/").json()["listings"][0]["area_is_verified"])

    def test_import_clears_previous_area_evidence_but_preserves_history(self):
        self.verify(self.offers[0])
        item = ScrapedProduct("milk-1", "Synthetic Milk 1L", self.offers[0].url, Decimal(105), availability="in_stock", delivery_area="Test district")
        PriceHistory.objects.create(listing=self.offers[0], price=100, checked_at=self.checked)
        updated, created = ingest(self.retailers[0], item)
        self.assertFalse(created)
        self.assertEqual(updated.pk, self.offers[0].pk)
        self.assertFalse(updated.area_is_verified)
        self.assertEqual(updated.delivery_area_key, "")
        self.assertEqual(updated.area_evidence_url, "")
        self.assertIsNone(updated.area_verified_at)
        self.assertEqual(updated.history.count(), 2)
        self.assertEqual(updated.history.last().price, 100)
        self.assertEqual(updated.history.first().price, 105)
        with self.assertRaises(ValidationError):
            ingest(self.retailers[0], replace(item, price=Decimal(-1)))
        self.assertEqual(updated.history.count(), 2)

    def test_api_and_pages_distinguish_unverified_and_verified_areas(self):
        data = self.client.get("/api/products/synthetic-milk/").json()
        self.assertTrue(data["has_unverified_areas"])
        self.assertEqual(data["comparison_area"], "")
        self.assertTrue(all(not offer["area_is_verified"] for offer in data["listings"]))
        response = self.client.get("/products/synthetic-milk/")
        self.assertContains(response, "About delivery coverage")
        self.assertContains(response, "Delivery coverage unverified", count=2)
        self.assertNotContains(response, 'class="lowest-tag"')
        self.assertContains(self.client.get("/"), "Lowest observed")
        for offer in self.offers:
            self.verify(offer)
        data = self.client.get("/api/products/synthetic-milk/").json()
        self.assertTrue(data["has_comparison"])
        self.assertEqual(data["comparison_area"], "Test district")
        self.assertTrue(all(offer["area_is_verified"] and offer["area_evidence_url"] and offer["area_verified_at"] for offer in data["listings"]))
        response = self.client.get("/products/synthetic-milk/")
        self.assertContains(response, "Compared for Test district")
        self.assertContains(response, "Area evidence", count=2)
        self.assertContains(response, 'class="lowest-tag"', count=1)

    def test_admin_validates_evidence_as_a_complete_observation(self):
        model_admin = ListingAdmin(RetailerListing, AdminSite())
        request = RequestFactory().get("/admin/")
        form_class = model_admin.get_form(request, obj=self.offers[0])
        offer = self.offers[0]
        data = {"product": self.product.pk, "retailer": self.retailers[0].pk, "external_id": offer.external_id,
                "original_title": offer.original_title, "url": offer.url, "current_price": "100.00", "currency": "PKR",
                "availability": "in_stock", "delivery_area": "Test district", "delivery_area_key": "pk-test-district",
                "last_checked_0": self.checked.strftime("%Y-%m-%d"), "last_checked_1": self.checked.strftime("%H:%M:%S")}
        form = form_class(data=data, instance=offer)
        self.assertFalse(form.is_valid())
        self.assertIn("Area verification requires", str(form.non_field_errors()))
        self.assertIn("area_is_verified", model_admin.readonly_fields)
        local_checked = timezone.localtime(self.checked)
        local_verified = timezone.localtime(self.verified)
        data.update({"area_evidence_url": offer.retailer.website + "/public-area-offer",
                     "last_checked_0": local_checked.strftime("%Y-%m-%d"), "last_checked_1": local_checked.strftime("%H:%M:%S"),
                     "area_verified_at_0": local_verified.strftime("%Y-%m-%d"), "area_verified_at_1": local_verified.strftime("%H:%M:%S")})
        form = form_class(data=data, instance=offer)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().area_is_verified)
        # Missing/invalid relation input must be a form error, never a server error.
        for retailer_id in ("", "999999"):
            with self.subTest(retailer=retailer_id):
                form = form_class(data={**data, "retailer": retailer_id}, instance=RetailerListing())
                self.assertFalse(form.is_valid())
                self.assertIn("retailer", form.errors)

    def test_public_delivery_review_is_dated_and_never_fetches_sources(self):
        call_command("seed_retailers", stdout=StringIO())
        before = (RetailerListing.objects.count(), PriceHistory.objects.count())
        with patch("requests.Session.request", side_effect=AssertionError("Page views must not fetch retailers")):
            response = self.client.get("/sources/")
            self.assertContains(response, 'id="delivery-coverage"')
            self.assertContains(response, "Reviewed 24 Oct 2026", count=2)
            self.assertContains(response, "shippable outside Karachi")
            self.assertContains(response, "Lahore")
            self.assertContains(response, "This does not verify the area of a collected price", count=2)
            self.assertEqual(self.client.get("/").status_code, 200)
            self.assertEqual(self.client.get("/api/products/").status_code, 200)
        self.assertEqual(before, (RetailerListing.objects.count(), PriceHistory.objects.count()))

    def test_demo_comparisons_remain_fictional_without_area_verification(self):
        call_command("seed_demo", stdout=StringIO())
        demo = decorate(get_product_queryset().get(slug="demo-olpers-milk-1l"))
        self.assertTrue(demo.has_comparison)
        self.assertFalse(demo.has_unverified_areas)
        self.assertTrue(all(not offer.area_is_verified for offer in demo.offers))
        response = self.client.get("/products/demo-olpers-milk-1l/")
        self.assertContains(response, "Demo comparison")
        self.assertNotContains(response, "Area evidence")
