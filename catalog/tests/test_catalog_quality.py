from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal
from io import StringIO
import json
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from catalog.models import Category, PriceHistory, Product, Retailer, RetailerListing
from catalog.services.catalog_quality import catalog_quality


class CatalogQualityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Dairy", slug="dairy")
        cls.retailer = Retailer.objects.create(name="QA source", slug="qa-source", website="https://example.com")
        cls.operator = User.objects.create_superuser("quality-operator", password=None)

    def product(self, slug="milk", **overrides):
        return Product.objects.create(**{"slug": slug, "canonical_name": "Olpers Milk 1L", "brand": "olpers",
                                         "quantity": Decimal("1000"), "unit": "ml", "category": self.category, **overrides})

    def listing(self, product, **overrides):
        return RetailerListing.objects.create(**{"product": product, "retailer": self.retailer,
            "external_id": product.slug, "original_title": product.canonical_name, "current_price": "325.00",
            "is_demo": product.is_demo, **overrides})

    def findings(self, code, **kwargs):
        return [row for row in catalog_quality(**kwargs)["findings"] if row["code"] == code]

    def get(self, **params):
        return self.client.get(reverse("admin:catalog_quality"), params)

    def test_consistent_product_and_normalized_listing_have_no_findings(self):
        product = self.product()
        self.listing(product, original_title="Olper's UHT Milk 1000ml")
        report = catalog_quality(now=datetime(2026, 10, 29, 21, 0, tzinfo=datetime_timezone.utc))
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["complete"])
        self.assertEqual(report["counts"]["products_scanned"], 1)
        self.assertEqual(report["as_of"], "2026-10-30T02:00:00+05:00")

    def test_missing_metadata_and_orphan_products_are_visible_without_guessed_values(self):
        product = self.product(canonical_name="Unknown groceries", brand="", quantity=None, unit="", category=None)
        report = catalog_quality()
        self.assertTrue({"missing_size", "missing_brand", "missing_category", "no_listings"}.issubset(report["by_check"]))
        product.refresh_from_db()
        self.assertIsNone(product.quantity)
        self.assertEqual(product.brand, "")

    def test_unknown_or_inconsistent_contents_never_enter_duplicate_groups(self):
        for slug, fields in [("unknown", {"quantity": None, "unit": ""}), ("unit-only", {"quantity": None}),
                             ("bad-unit", {"unit": "L"}), ("piece-fraction", {"unit": "pc", "quantity": Decimal("1.5")})]:
            self.product(slug, **fields)
        self.assertEqual(len(self.findings("invalid_contents")), 3)
        self.assertEqual(self.findings("potential_duplicate"), [])

    def test_canonical_brand_size_variant_and_packaging_conflicts(self):
        for slug, fields in [("wrong-brand", {"brand": "nestle"}), ("wrong-size", {"quantity": Decimal("500")}),
                             ("wrong-count", {"pack_count": 6}),
                             ("wrong-variant", {"canonical_name": "Olpers Chocolate Milk 1L", "variant": "strawberry"}),
                             ("wrong-package", {"canonical_name": "Olpers Milk Bottle 1L", "packaging": "pouch"})]:
            self.product(slug, **fields)
        rows = self.findings("canonical_conflict")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["severity"] == "error" for row in rows))
        self.assertEqual(self.findings("potential_duplicate"), [])

    def test_title_without_verifiable_size_and_non_latin_names_stay_uncertain(self):
        self.product("no-size", canonical_name="Olpers Milk")
        self.product("unicode", canonical_name="دودھ", brand="مقامی")
        self.assertEqual(len(self.findings("canonical_uncertain")), 2)
        self.assertEqual(self.findings("potential_duplicate"), [])

    def test_exact_normalized_duplicates_ignore_category_but_guard_variant_pack_size_and_barcode(self):
        self.product("milk-a")
        self.product("milk-b", canonical_name="Olper's UHT Milk 1000ml", category=None)
        self.product("small", canonical_name="Olpers Milk 250ml", quantity=Decimal("250"))
        self.product("chocolate", canonical_name="Olpers Chocolate Milk 1L", variant="chocolate")
        self.product("multi", canonical_name="Olpers Milk 6 x 1L", pack_count=6)
        rows = self.findings("potential_duplicate")
        self.assertEqual(len(rows), 1)
        self.assertEqual([p["slug"] for p in rows[0]["products"]], ["milk-a", "milk-b"])

    def test_variant_aliases_are_not_misreported_as_conflicts(self):
        product = self.product(canonical_name="National Chili Powder 100g", brand="national", quantity=Decimal("100"), unit="g", variant="chilli")
        self.listing(product, original_title="National Chilli Powder 100g")
        self.assertEqual(self.findings("canonical_conflict"), [])
        self.assertEqual(self.findings("listing_conflict"), [])

    def test_conflicting_barcodes_and_shared_barcodes_have_explicit_findings(self):
        self.product("barcode-a", gtin="1234567890123")
        self.product("barcode-b", gtin="1234567890124")
        self.product("small", canonical_name="Olpers Milk 250ml", quantity=Decimal("250"), gtin="1234567890123")
        self.product("malformed", canonical_name="Dalda Oil 1L", brand="dalda", gtin="not-a-code")
        self.assertEqual(len(self.findings("barcode_conflict")), 1)
        self.assertEqual(self.findings("potential_duplicate"), [])
        self.assertEqual(self.findings("shared_barcode")[0]["severity"], "error")
        self.assertEqual(len(self.findings("barcode_format")), 1)

    def test_similar_names_sharing_a_barcode_are_review_warnings_not_proven_pack_conflicts(self):
        self.product("one", canonical_name="Olpers Fresh Milk 1L", gtin="1234567890123")
        self.product("two", canonical_name="Olpers Freshh Milk 1L", gtin="1234567890123")
        self.assertEqual(self.findings("shared_barcode")[0]["severity"], "warning")

    def test_listing_brand_contents_variant_and_packaging_drift_are_conflicts(self):
        product = self.product(canonical_name="Olpers Milk Bottle 1L", packaging="bottle")
        for index, title in enumerate(["Nestle Milk Bottle 1L", "Olpers Milk Bottle 500ml", "Olpers Milk Bottle 6 x 1L",
                                       "Olpers Chocolate Milk Bottle 1L", "Olpers Milk Pouch 1L"]):
            self.listing(product, external_id=str(index), original_title=title)
        rows = self.findings("listing_conflict")
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["listings"][0]["id"] for row in rows))

    def test_unverifiable_or_fuzzy_listing_names_are_review_warnings(self):
        product = self.product(canonical_name="Olpers Fresh Milk 1L")
        for index, title in enumerate(["Fresh Milk 1L", "Olpers Freshh Milk 1L", "Olpers Fresh Milk"]):
            self.listing(product, external_id=str(index), original_title=title)
        rows = self.findings("listing_uncertain")
        self.assertEqual(len(rows), 3)
        self.assertTrue(all("name_similarity" in row["evidence"] for row in rows))

    def test_similar_products_use_hard_guards_and_never_compare_catalogs(self):
        self.product("one", canonical_name="Olpers Fresh Milk 1L")
        self.product("two", canonical_name="Olpers Freshh Milk 1L")
        self.product("other-size", canonical_name="Olpers Freshh Milk 250ml", quantity=Decimal("250"))
        self.product("demo", canonical_name="Olpers Freshh Milk 1L", is_demo=True)
        rows = self.findings("similar_products")
        self.assertEqual(len(rows), 1)
        self.assertEqual({p["slug"] for p in rows[0]["products"]}, {"one", "two"})
        self.assertGreaterEqual(Decimal(rows[0]["evidence"]["name_similarity"]), 80)

    def test_source_flag_conflicts_are_visible_from_either_affected_catalog(self):
        live, demo = self.product("live"), self.product("demo", is_demo=True)
        self.listing(live, is_demo=True)
        self.listing(demo, is_demo=False)
        for source in ("demo", "live"):
            self.assertEqual(len(self.findings("source_mismatch", source=source)), 2)
            self.assertEqual(self.findings("potential_duplicate", source=source), [])
            self.assertEqual(catalog_quality(source=source)["counts"]["products_total"], 1)

    def test_filtering_occurs_before_output_cap_and_keeps_global_summary(self):
        self.product()
        with patch("catalog.services.catalog_quality.FINDING_LIMIT", 1):
            report = catalog_quality(check="no_listings")
        self.assertEqual(report["counts"]["findings_selected"], 1)
        self.assertEqual(report["findings"][0]["code"], "no_listings")
        self.assertEqual(report["by_check"]["no_listings"], 1)

    def test_all_scan_limits_are_explicit_and_counts_are_not_silent_success(self):
        one, two = self.product("one"), self.product("two")
        self.listing(one)
        self.listing(two)
        for constant, limit in [("PRODUCT_LIMIT", 1), ("LISTING_LIMIT", 1), ("PAIR_LIMIT", 0), ("FINDING_LIMIT", 0)]:
            with self.subTest(constant=constant), patch("catalog.services.catalog_quality." + constant, limit):
                report = catalog_quality()
                self.assertFalse(report["complete"])
                self.assertTrue(any(report["limits"].values()))
        with patch("catalog.services.catalog_quality.PRODUCT_LIMIT", 1):
            report = catalog_quality()
        self.assertEqual(report["counts"]["products_total"], 2)
        self.assertEqual(report["counts"]["products_scanned"], 1)

    def test_large_group_references_are_shortened_without_losing_group_size(self):
        for index in range(3):
            self.product(f"milk-{index}")
        with patch("catalog.services.catalog_quality.REFERENCE_LIMIT", 1):
            row = self.findings("potential_duplicate")[0]
        self.assertTrue(row["references_limited"])
        self.assertEqual(row["product_count"], 3)
        self.assertEqual(len(row["products"]), 1)

    def test_report_and_command_are_read_only_bounded_queries_and_do_not_collect(self):
        product = self.product()
        listing = self.listing(product)
        PriceHistory.objects.create(listing=listing, price="325.00")
        before = (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count())
        with CaptureQueriesContext(connection) as queries, patch("requests.sessions.Session.send", side_effect=AssertionError("No network")):
            report = catalog_quality()
        self.assertEqual(len(queries), 4)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT") for query in queries))
        json.dumps(report)
        output = StringIO()
        call_command("catalog_quality", source="live", format="json", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["counts"], report["counts"])
        self.assertEqual(before, (Product.objects.count(), RetailerListing.objects.count(), PriceHistory.objects.count()))

    def test_cli_text_filters_and_partial_notice(self):
        self.product("one")
        self.product("two")
        output = StringIO()
        with patch("catalog.services.catalog_quality.PAIR_LIMIT", 0):
            call_command("catalog_quality", check="potential_duplicate", stdout=output)
        self.assertIn("PARTIAL REPORT", output.getvalue())
        self.assertIn("potential_duplicate", output.getvalue())
        self.assertNotIn("[warning] no_listings", output.getvalue())

    def test_permissions_require_active_staff_and_all_three_model_permissions(self):
        url = reverse("admin:catalog_quality")
        self.assertEqual(self.client.get(url).status_code, 302)
        user = User.objects.create_user("reviewer", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.get().status_code, 403)
        for model in ["product", "retailerlisting", "retailer"]:
            user.user_permissions.add(Permission.objects.get(codename="view_" + model))
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertContains(self.client.get(reverse("admin:catalog_product_changelist")), "Catalog quality")
        User.objects.filter(pk=user.pk).update(is_active=False)
        self.assertEqual(self.get().status_code, 302)

    def test_admin_filter_errors_never_fall_back_to_unfiltered_report(self):
        self.client.force_login(self.operator)
        for params in [{"source": "all"}, {"severity": "severe"}, {"check": "typo"}, {"format": "csv"}]:
            response = self.get(**params)
            self.assertEqual(response.status_code, 400)
            self.assertIsNone(response.context["report"])

    def test_admin_partial_report_warns_even_when_filter_has_no_retained_findings(self):
        self.client.force_login(self.operator)
        self.product("one")
        self.product("two")
        with patch("catalog.services.catalog_quality.PRODUCT_LIMIT", 1):
            response = self.get(check="listing_conflict")
        self.assertContains(response, "Partial report.")
        self.assertContains(response, "cannot establish a clean catalog")
        self.assertEqual(response.context["report"]["findings"], [])

    def test_admin_pagination_export_escape_links_and_read_only_methods(self):
        self.client.force_login(self.operator)
        for index in range(27):
            self.product(f"milk-{index}", canonical_name='<img src=x onerror="alert(1)"> Groceries')
        response = self.get(check="canonical_uncertain", source="live")
        self.assertEqual(response.context["page_obj"].paginator.count, 27)
        self.assertEqual(len(response.context["page_obj"]), 25)
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, '<img src=x')
        self.assertContains(response, "check=canonical_uncertain")
        self.assertEqual(len(self.get(check="canonical_uncertain", page="2").context["page_obj"]), 2)
        exported = self.get(format="json", severity="warning", check="canonical_uncertain")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(len(exported.json()["findings"]), 27)
        self.assertIn("attachment", exported["Content-Disposition"])
        self.assertIn("no-store", exported["Cache-Control"])
        self.assertEqual(self.client.head(reverse("admin:catalog_quality")).status_code, 200)
