"""Exact size-family membership, rational rates and observation-level safeguards."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from bs4 import BeautifulSoup
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.matching.normalization import identify
from catalog.models import AdminPriceRefresh, Category, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from catalog.services.pack_comparison import family_key, pack_comparison


@override_settings(PRICE_STALE_HOURS=48)
class PackComparisonTests(TestCase):
    def setUp(self):
        call_command("seed_retailers", stdout=StringIO())
        self.now = timezone.now()
        self.category = Category.objects.create(name="Dairy", slug="dairy")
        self.reference = self.product("Olpers Milk 1L")

    def product(self, title, **overrides):
        identity = identify(title)
        data = {"canonical_name": title, "brand": identity.brand, "quantity": identity.quantity,
                "unit": identity.unit, "pack_count": identity.pack_count,
                "variant": " ".join(sorted(identity.variants)), "packaging": " ".join(sorted(identity.packaging)),
                "category": self.category, "slug": "pack-test-" + str(Product.objects.count())}
        data.update(overrides)
        if data["quantity"] is not None:
            data["quantity"] = Decimal(str(data["quantity"]))
        return Product.objects.create(**data)

    def offer(self, product, price="350", *, source="jalal-sons", hours=1, stock="in_stock", verified=False, **overrides):
        retailer = Retailer.objects.get(slug=source)
        data = {"product": product, "retailer": retailer, "original_title": product.canonical_name,
                "external_id": f"pack-{product.pk}-{RetailerListing.objects.count()}", "current_price": price,
                "availability": stock, "last_checked": self.now - timedelta(hours=hours), "is_demo": product.is_demo,
                "delivery_area": "Demo area" if product.is_demo else "Delivery area unverified",
                "url": retailer.website.rstrip("/") + "/product/pack-example"}
        if verified:
            data.update(delivery_area="Test branch scope", delivery_area_key="test-scope",
                        area_evidence_url=retailer.website.rstrip("/") + "/delivery-evidence", area_verified_at=self.now)
        return RetailerListing.objects.create(**{**data, **overrides})

    def compare(self, product=None, **kwargs):
        return pack_comparison(product or self.reference, now=self.now, **kwargs)

    def test_exact_family_ignores_size_and_pack_count_and_uses_total_contents(self):
        single = self.product("Olpers Milk 250ml")
        multi = self.product("Olpers Milk 6 x 250ml")
        self.offer(self.reference, "325")
        self.offer(single, "85")
        self.offer(multi, "510")
        result = self.compare()
        self.assertEqual(result["alternative_pack_count"], 2)
        self.assertEqual({row["total_contents"] for row in result["rows"]}, {"0.25 L", "1 L", "1.5 L"})
        self.assertEqual({row["product_slug"]:row["standard_unit_price"]["amount"] for row in result["rows"]},
                         {self.reference.slug:"325.00", single.slug:"340.00", multi.slug:"340.00"})
        self.assertEqual([row["pack_count"] for row in result["rows"]], [1, 1, 6])
        self.assertFalse(result["ranking_available"])
        self.assertIn("unverified", result["ranking_note"])

    def test_brand_name_variant_packaging_dimension_and_category_must_agree(self):
        self.offer(self.reference)
        for title, changes in [
            ("Nestle Milk 250ml", {}), ("Olpers Cream 250ml", {}), ("Olpers Chocolate Milk 250ml", {}),
            ("Olpers Milk Pouch 250ml", {}), ("Olpers Milk 250g", {}), ("Olpers Milk 250ml", {"category":None}),
            ("Olpers Milk 250ml", {"variant":"organic"}), ("Olpers Milk 250ml", {"packaging":"bottle"}),
        ]:
            other = self.product(title, **changes)
            self.offer(other)
        result = self.compare()
        self.assertEqual(result["displayed_product_count"], 1)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["alternative_pack_count"], 0)

    def test_size_metadata_drift_unknown_identity_and_fractional_counts_do_not_form_a_family(self):
        for title, changes in [("Olpers Milk", {}), ("Olpers Milk 250ml", {"quantity":500}),
                               ("Milk 250ml", {"brand":""}), ("Olpers Milk 250ml", {"pack_count":6}),
                               ("Tapal Tea Bags 1.5pc", {})]:
            other = self.product(title, **changes)
            self.offer(other)
            self.assertIsNone(family_key(other))
            result = self.compare(other)
            self.assertTrue(result["limited"])
            self.assertFalse(result["ranking_available"])
            self.assertTrue(all(row["standard_unit_price"] is None for row in result["rows"]))

    def test_listing_title_drift_withholds_its_rate_and_eligibility(self):
        small = self.product("Olpers Milk 250ml")
        self.offer(self.reference, verified=True)
        self.offer(small, "10", verified=True, original_title="Olpers Milk 1L")
        row = next(row for row in self.compare()["rows"] if row["product_slug"] == small.slug)
        self.assertFalse(row["eligible"])
        self.assertIsNone(row["standard_unit_price"])
        self.assertIn("Product or listing identity needs review", row["exclusions"])

    def test_eligible_verified_scope_highlights_exact_lowest_rate_and_exact_ties(self):
        small = self.product("Olpers Milk 250ml")
        self.offer(self.reference, "320", verified=True)
        self.offer(small, "80", source="cartpk", verified=True)
        result = self.compare()
        self.assertTrue(result["ranking_available"])
        self.assertEqual(sum(row["is_lowest_unit_rate"] for row in result["rows"]), 2)
        RetailerListing.objects.filter(product=small).update(current_price="85")
        result = self.compare()
        self.assertEqual([row["product_slug"] for row in result["rows"] if row["is_lowest_unit_rate"]], [self.reference.slug])
        self.assertEqual(result["comparison_area"], "Test branch scope")

    def test_one_unverified_or_conflicting_area_withholds_the_overall_highlight(self):
        small = self.product("Olpers Milk 250ml")
        self.offer(self.reference, verified=True)
        other = self.offer(small, "80", source="cartpk", verified=True)
        extra = self.offer(small, "1", source="naheed")
        self.assertFalse(self.compare()["ranking_available"])
        extra.delete()
        other.delivery_area_key = "different-scope"
        other.save()
        self.assertFalse(self.compare()["ranking_available"])
        other.delivery_area_key = "test-scope"
        other.delivery_area = "Different branch label"
        other.save()
        self.assertFalse(self.compare()["ranking_available"])
        # Distinct non-Latin labels must not collapse to an empty ASCII label.
        RetailerListing.objects.filter(product=self.reference).update(delivery_area="لاہور")
        other.delivery_area = "کراچی"
        other.save()
        self.assertFalse(self.compare()["ranking_available"])

    def test_stale_future_out_of_stock_unknown_and_exact_cutoff_are_explicit(self):
        self.offer(self.reference, "350", hours=48, verified=True)
        small = self.product("Olpers Milk 250ml")
        for price, changes, message in [
            ("1", {"hours":49}, "Stale observation"), ("2", {"hours":-1}, "Future check time needs review"),
            ("3", {"stock":"out_of_stock"}, "Out of stock"), ("4", {"stock":"unknown"}, "Availability unknown"),
        ]:
            listing = self.offer(small, price, **changes)
            row = next(row for row in self.compare()["rows"] if row["listing_id"] == listing.pk)
            self.assertFalse(row["eligible"])
            self.assertIn(message, row["exclusions"])
            self.assertIsNotNone(row["standard_unit_price"])
        result = self.compare(sort="unit_price")
        self.assertTrue(result["rows"][0]["eligible"])
        self.assertEqual(result["rows"][0]["product_slug"], self.reference.slug)
        self.assertFalse(result["ranking_available"])

    def test_display_rounding_never_creates_a_false_unique_winner(self):
        reference = self.product("Olpers Milk 3000ml")
        other = self.product("Olpers Milk 6001ml")
        self.offer(reference, "1", verified=True)
        self.offer(other, "2", verified=True)
        result = self.compare(reference)
        self.assertEqual({row["standard_unit_price"]["amount"] for row in result["rows"]}, {"0.33"})
        self.assertFalse(result["ranking_available"])
        self.assertIn("Rounded unit rates overlap", result["ranking_note"])

    def test_small_positive_rates_stay_less_than_one_paisa_and_are_not_free(self):
        reference = self.product("Olpers Milk 1000L")
        other = self.product("Olpers Milk 2000L")
        self.offer(reference, "0.01", verified=True)
        self.offer(other, "0.01", verified=True)
        result = self.compare(reference)
        self.assertFalse(result["ranking_available"])
        self.assertTrue(all(row["standard_unit_price"]["display"] == "< Rs. 0.01/L" for row in result["rows"]))

    def test_mass_and_piece_families_remain_separate_and_include_multipacks(self):
        for titles, prices, rates, unit in [
            (("National Salt 500g", "National Salt 2 x 500g"), ("100","180"), {"200.00","180.00"}, "kg"),
            (("Tapal Danedar Tea Bags 100pc", "Tapal Danedar Tea Bags 50pc"), ("900","500"), {"9.00","10.00"}, "item"),
        ]:
            left, right = [self.product(title) for title in titles]
            self.offer(left, prices[0])
            self.offer(right, prices[1])
            result = self.compare(left)
            self.assertEqual(result["displayed_product_count"], 2)
            self.assertEqual({row["standard_unit_price"]["amount"] for row in result["rows"]}, rates)
            self.assertTrue(all(row["standard_unit_price"]["unit"] == unit for row in result["rows"]))

    def test_gtins_may_differ_across_sizes_but_conflicting_same_pack_codes_are_not_assumed_equal(self):
        self.reference.gtin = "1234567890123"
        self.reference.save()
        self.offer(self.reference)
        other = self.product("Olpers Milk 250ml", gtin="9876543210987")
        self.offer(other)
        duplicate = self.product("Olpers Milk 1L", gtin="9876543210987")
        self.offer(duplicate)
        self.assertEqual({row["product_slug"] for row in self.compare()["rows"]}, {self.reference.slug,other.slug})
        third = self.product("Olpers Milk 250ml", gtin="1111111111111")
        self.offer(third)
        result = self.compare()
        self.assertFalse(result["ranking_available"])
        self.assertIn("Conflicting barcodes", result["notice"])

    def test_demo_and_live_flags_remain_separate_and_demo_links_are_disabled(self):
        call_command("seed_demo", stdout=StringIO())
        self.now = timezone.now()
        self.offer(self.reference)
        demo = Product.objects.get(slug="demo-olpers-milk-1l")
        self.offer(self.reference, is_demo=True)
        self.offer(demo, source="cartpk", is_demo=False)
        live_result = self.compare()
        self.assertEqual(len(live_result["rows"]), 1)
        demo_result = self.compare(demo)
        self.assertEqual(demo_result["source"], "demo")
        self.assertEqual(demo_result["displayed_product_count"], 2)
        self.assertTrue(all(row["is_demo"] and not row["url"] for row in demo_result["rows"]))
        self.assertTrue(demo_result["ranking_available"])
        self.assertIn("fictional", demo_result["ranking_note"])
        response = self.client.get(reverse("pack-comparison", args=[demo.slug]))
        self.assertContains(response, "Fictional Demo comparison")
        self.assertNotContains(response, "Visit retailer")

    def test_candidate_product_and_listing_limits_fail_closed_without_silent_winners(self):
        self.offer(self.reference, verified=True)
        small = self.product("Olpers Milk 250ml")
        self.offer(small, verified=True)
        for name, limit in (("CANDIDATE_LIMIT",1),("PRODUCT_LIMIT",1),("LISTING_LIMIT",1)):
            with self.subTest(limit=name), patch("catalog.services.pack_comparison."+name,limit):
                result = self.compare()
                self.assertTrue(result["limited"])
                self.assertFalse(result["ranking_available"])
                self.assertFalse(any(row["is_lowest_unit_rate"] for row in result["rows"]))

    def test_no_listing_unknown_size_and_single_format_have_useful_empty_states(self):
        result = self.compare()
        self.assertEqual(result["rows"][0]["exclusions"], ["No collected listings"])
        self.assertFalse(result["ranking_available"])
        response = self.client.get(reverse("pack-comparison",args=[self.reference.slug]))
        self.assertContains(response,"No other compatible pack formats")
        self.reference.quantity = None
        self.reference.unit = ""
        self.reference.save()
        response = self.client.get(reverse("pack-comparison",args=[self.reference.slug]))
        self.assertContains(response,"identity or pack contents need review")
        self.assertContains(response,"Unit price unavailable")

    def test_views_api_sorting_methods_cache_and_links(self):
        small = self.product("Olpers Milk 250ml")
        self.offer(self.reference,"325")
        self.offer(small,"85")
        url = reverse("api-pack-comparison",args=[self.reference.slug])
        data = self.client.get(url,{"sort":"pack_price"}).json()
        self.assertEqual(data["rows"][0]["price"],"85.00")
        data = self.client.get(url,{"sort":"unit_price"}).json()
        self.assertEqual(data["rows"][0]["price"],"325.00")
        page = reverse("pack-comparison",args=[self.reference.slug])
        self.assertIn("no-store", self.client.get(page)["Cache-Control"])
        self.assertIn("no-store", self.client.get(url)["Cache-Control"])
        self.assertEqual(self.client.get(page,{"sort":"bad"}).status_code,400)
        self.assertEqual(self.client.get(url,{"sort":"bad"}).status_code,400)
        self.assertEqual(self.client.post(page,{}).status_code,405)
        self.assertEqual(self.client.post(url,{}).status_code,405)
        self.assertEqual(self.client.get("/products/missing/pack-comparison/").status_code,404)
        self.assertEqual(self.client.get("/api/products/missing/pack-comparison/").status_code,404)
        self.assertContains(self.client.get(reverse("product-detail",args=[self.reference.slug])),page)
        self.assertContains(self.client.get("/?source=live"),page)

    def test_summary_is_two_bounded_queries_and_does_not_write_or_fetch(self):
        self.offer(self.reference)
        for size in (250,500,1500):
            other = self.product(f"Olpers Milk {size}ml")
            self.offer(other)
        with self.assertNumQueries(2):
            result = self.compare()
            self.assertEqual(result["displayed_product_count"],4)
        models=(Product,RetailerListing,PriceHistory,Retailer,ScrapeRun,AdminPriceRefresh)
        before=[list(model.objects.order_by("pk").values()) for model in models]
        with patch("requests.sessions.Session.send",side_effect=AssertionError("No retailer requests")):
            for route in ("pack-comparison","api-pack-comparison"):
                self.assertEqual(self.client.get(reverse(route,args=[self.reference.slug])).status_code,200)
        self.assertEqual(before,[list(model.objects.order_by("pk").values()) for model in models])

    def test_source_links_and_escaped_titles_cannot_inject_a_purchase_link(self):
        self.reference.canonical_name = '<script>alert("x")</script> Olpers Milk 1L'
        self.reference.save()
        self.offer(self.reference,url="javascript:alert('bad')")
        response=self.client.get(reverse("pack-comparison",args=[self.reference.slug]))
        soup=BeautifulSoup(response.content,"html.parser").select_one("[data-pack-comparison]")
        self.assertFalse(soup.select("script"))
        self.assertFalse(soup.select('a[href^="javascript:"]'))
        self.assertContains(response,"&lt;script&gt;")
