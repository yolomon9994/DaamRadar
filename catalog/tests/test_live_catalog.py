from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from django.core.management import call_command
from django.test import TestCase

from catalog.models import PriceHistory, Product, Retailer, RetailerListing
from catalog.scraping.adapters import JalalSonsAdapter, NaheedAdapter
from catalog.services.catalog import decorate, get_product_queryset
from catalog.services.ingestion import ingest


class CollectedCatalogTests(TestCase):
    """Real-source format extracts go through the same ingestion path, offline."""

    def setUp(self):
        call_command("seed_demo", stdout=StringIO())
        self.listings = []
        cases = [
            ("naheed", NaheedAdapter(), "naheed_milk.html", "https://www.naheed.pk/olper-s-full-cream-milk-1000ml"),
            ("jalal-sons", JalalSonsAdapter(), "jalal_milk.html", "https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398"),
        ]
        for slug, adapter, fixture, url in cases:
            client = MagicMock()
            client.get_html.return_value = (Path(__file__).parent / "fixtures" / fixture).read_text(encoding="utf-8")
            listing, _ = ingest(Retailer.objects.get(slug=slug), adapter.collect(client, url))
            self.listings.append(listing)

    def test_equivalent_real_source_formats_match_and_do_not_mix_with_demo(self):
        self.assertEqual(self.listings[0].product_id, self.listings[1].product_id)
        self.assertNotEqual(self.listings[0].product_id, Product.objects.get(slug="demo-olpers-milk-1l").pk)
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 2)
        self.assertEqual(PriceHistory.objects.filter(listing__is_demo=False).count(), 2)
        product = decorate(get_product_queryset().get(pk=self.listings[0].product_id))
        self.assertTrue(product.has_mixed_areas)
        self.assertFalse(product.best_ids)
        self.assertEqual([str(offer.current_price) for offer in product.offers], ["350.00", "380.00"])

    def test_home_and_api_prefer_collected_data_once_present(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source"], "live")
        self.assertContains(response, "2 retailer listings collected")
        self.assertNotContains(response, "No live prices have been collected")
        self.assertEqual(self.client.get("/api/products/").json()["count"], 1)
        self.assertFalse(self.client.get("/api/products/").json()["results"][0]["is_demo"])
        self.assertEqual(self.client.get("/api/products/?source=demo").json()["count"], 12)
        self.assertEqual(self.client.get("/?source=demo").context["source"], "demo")

    def test_collected_detail_has_real_links_and_area_warning(self):
        slug = self.listings[0].product.slug
        response = self.client.get(f"/products/{slug}/")
        self.assertContains(response, "Visit retailer", count=2)
        self.assertContains(response, "Delivery areas may differ or be unverified")
        self.assertContains(response, self.listings[0].url)
        self.assertNotContains(response, "SAMPLE LOW")
        sources = self.client.get("/sources/")
        self.assertContains(sources, "2 collected retailer listings")
        self.assertNotContains(sources, "No live retailer prices have been collected")

    def test_single_retailer_is_an_observation_not_a_winning_comparison(self):
        self.listings[0].delete()
        product = decorate(get_product_queryset().get(pk=self.listings[1].product_id))
        self.assertFalse(product.has_comparison)
        self.assertFalse(product.best_ids)
        response = self.client.get("/")
        self.assertContains(response, "Observed listed price")
        self.assertNotContains(response, "Sample low")
