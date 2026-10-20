from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from catalog.models import PriceHistory, Retailer, RetailerListing, ScrapeRun
from catalog.scraping.adapters import AlFatahAdapter, JalalSonsAdapter, NaheedAdapter
from catalog.scraping.client import PoliteClient
from catalog.scraping.parsers import parse_product_html
from catalog.scraping.types import CollectionError

HTML = (Path(__file__).parent / "fixtures" / "product.html").read_text(encoding="utf-8")
NAHEED_HTML = (Path(__file__).parent / "fixtures" / "naheed_milk.html").read_text(encoding="utf-8")
JALAL_HTML = (Path(__file__).parent / "fixtures" / "jalal_milk.html").read_text(encoding="utf-8")
NAHEED_URL = "https://www.naheed.pk/olper-s-full-cream-milk-1000ml"
JALAL_URL = "https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398"


class ParserTests(SimpleTestCase):
    def test_observed_retailer_formats_and_no_rich_content_retained(self):
        for adapter, html, url, price in [(NaheedAdapter(), NAHEED_HTML, NAHEED_URL, "380"),
                                          (JalalSonsAdapter(), JALAL_HTML, JALAL_URL, "350.00")]:
            with self.subTest(url=url):
                client = MagicMock()
                client.get_html.return_value = html
                item = adapter.collect(client, url)
                self.assertEqual(str(item.price), price)
                self.assertEqual(item.availability, "in_stock")
                self.assertEqual(item.image, "")
                self.assertEqual(item.url, url)
                self.assertIn("unverified", item.delivery_area)
                client.get_html.assert_called_once_with(url)

    def test_adapter_rejects_external_utility_and_query_urls_before_fetch(self):
        for adapter, urls in [(NaheedAdapter(), [NAHEED_URL + "?brand=test", "https://evil.test/milk", "http://www.naheed.pk/milk", "https://www.naheed.pk/catalog/product/view/1"]),
                              (JalalSonsAdapter(), [JALAL_URL + "#option", "https://www.jalalsons.com.pk/api/item", "https://www.jalalsons.com.pk/product/fake"] )]:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(CollectionError):
                    client = MagicMock()
                    adapter.collect(client, url)
                client.get_html.assert_not_called()

    def test_heading_and_structured_title_must_agree(self):
        client = MagicMock()
        client.get_html.return_value = NAHEED_HTML.replace("<h1>Olper's Full Cream Milk, 1000ml</h1>", "<h1>Choose a branch</h1>")
        with self.assertRaises(CollectionError):
            NaheedAdapter().collect(client, NAHEED_URL)

    def test_saved_synthetic_fixture(self):
        product = AlFatahAdapter.parse_saved_html(HTML, "https://alfatah.pk/products/example")
        self.assertEqual(str(product.price), "325.50")
        self.assertEqual(product.currency, "PKR")
        self.assertEqual(product.availability, "in_stock")
        self.assertEqual(product.brand, "Olper's")
        self.assertEqual(product.image, "https://alfatah.pk/images/milk.jpg")

    def test_changed_layout_missing_fields_and_ambiguous_offers(self):
        for html in ["<html>new layout</html>", '<script type="application/ld+json">not json</script>',
                     HTML.replace('"PKR"', '"USD"'), HTML.replace('"325.50"', '"NaN"'),
                     HTML.replace('"Offer"', '"AggregateOffer"'), HTML + HTML,
                     HTML.replace('"name":"Olper\'s Full Cream Milk 1000ml"', '"name":""')]:
            with self.subTest(html=html[:80]), self.assertRaises(CollectionError):
                parse_product_html(html, "https://alfatah.pk/products/example")


@override_settings(SCRAPER_CONTACT="test@example.com", SCRAPER_DELAY_SECONDS=5)
class ClientTests(SimpleTestCase):
    @override_settings(SCRAPER_CONTACT="https://github.com/example/project")
    def test_public_project_url_is_supported_as_crawler_identity(self):
        client = PoliteClient("https://www.naheed.pk")
        self.assertIn("(+https://github.com/example/project)", client.user_agent)

    def test_wildcards_allow_precedence_and_repeated_groups_are_respected(self):
        client = PoliteClient("https://www.naheed.pk")
        rules = "User-agent: *\nAllow: /\n\nUser-agent: *\nDisallow: /*?*brand=\nDisallow: /private/\nAllow: /private/public$"
        with patch.object(client, "_request", return_value=(rules, "text/plain")) as request:
            with self.assertRaises(CollectionError):
                client.get_html(NAHEED_URL + "?brand=x")
            request.assert_called_once()
        self.assertTrue(client.robots.can_fetch("https://www.naheed.pk/private/public", client.user_agent))
        self.assertFalse(client.robots.can_fetch("https://www.naheed.pk/private/secret", client.user_agent))

    def test_unverified_robots_and_denied_paths_fail_closed(self):
        client = PoliteClient("https://alfatah.pk")
        with patch.object(client, "_request", return_value=("<html>location selector</html>", "text/html")) as request:
            with self.assertRaises(CollectionError):
                client.get_html("https://alfatah.pk/products/milk")
            self.assertEqual(request.call_count, 1)
        client = PoliteClient("https://alfatah.pk")
        with patch.object(client, "_request", return_value=("User-agent: *\nDisallow: /products/", "text/plain")) as request:
            with self.assertRaises(CollectionError):
                client.get_html("https://alfatah.pk/products/milk")
            self.assertEqual(request.call_count, 1)

    def test_robots_crawl_delay_is_respected(self):
        client = PoliteClient("https://alfatah.pk")
        with patch.object(client, "_request", side_effect=[("User-agent: *\nAllow: /\nCrawl-delay: 15", "text/plain"), (HTML, "text/html")]):
            self.assertEqual(client.get_html("https://alfatah.pk/products/milk"), HTML)
        self.assertEqual(client.delay, 15)

    def test_rate_limit_and_access_denials_are_not_retried(self):
        for status in [301, 403, 429, 500]:
            with self.subTest(status=status):
                client = PoliteClient("https://alfatah.pk")
                response = MagicMock()
                response.__enter__.return_value = response
                response.status_code = status
                with patch.object(client.session, "get", return_value=response) as request:
                    with self.assertRaises(CollectionError):
                        client._request("https://alfatah.pk/products/milk")
                    request.assert_called_once()
                    self.assertFalse(request.call_args.kwargs["allow_redirects"])

    def test_timeouts_and_external_origins(self):
        client = PoliteClient("https://alfatah.pk")
        with patch.object(client.session, "get", side_effect=requests.Timeout):
            with self.assertRaises(CollectionError):
                client._request("https://alfatah.pk/products/milk")
        with patch.object(client.session, "get") as request:
            with self.assertRaises(CollectionError):
                client._request("https://other.test/")
            request.assert_not_called()

    def test_delay_between_requests(self):
        client = PoliteClient("https://alfatah.pk")
        client.last_request = 100
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.iter_content.return_value = [b"<html>test</html>"]
        response.encoding = "utf-8"
        response.headers = {"Content-Type": "text/html"}
        with patch("catalog.scraping.client.time.monotonic", return_value=102), patch("catalog.scraping.client.time.sleep") as sleep, patch.object(client.session, "get", return_value=response):
            client._request("https://alfatah.pk/products/milk")
            sleep.assert_called_once_with(3)


class ScrapeCommandTests(TestCase):
    @override_settings(SCRAPING_ENABLED=True, SCRAPER_CONTACT="test@example.com")
    def test_all_unvalidated_sources_block_without_network_and_audit(self):
        call_command("seed_retailers", stdout=StringIO())
        Retailer.objects.update(collection_enabled=True, status="enabled")
        with patch("requests.Session.get") as request:
            for slug in ["naheed", "springs", "alfatah"]:
                with self.subTest(slug=slug), self.assertRaises(CommandError):
                    call_command("scrape", slug, url=[f"https://{slug}.pk/products/test"])
            request.assert_not_called()
        self.assertEqual(ScrapeRun.objects.filter(status="blocked").count(), 3)
        self.assertTrue(all(run.completed_at is not None and run.error for run in ScrapeRun.objects.all()))

    @override_settings(SCRAPING_ENABLED=False)
    def test_available_adapter_still_requires_explicit_configuration(self):
        call_command("seed_retailers", stdout=StringIO())
        with patch("requests.Session.get") as request, self.assertRaises(CommandError):
            call_command("scrape", "jalal-sons", url=[JALAL_URL])
        request.assert_not_called()
        self.assertEqual(ScrapeRun.objects.get().status, "blocked")

    @override_settings(SCRAPING_ENABLED=True)
    def test_manual_collection_updates_listing_and_records_each_observation(self):
        call_command("seed_retailers", stdout=StringIO())
        Retailer.objects.filter(slug="jalal-sons").update(status="enabled", collection_enabled=True)
        with patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.return_value = JALAL_HTML
            for _ in range(2):
                call_command("scrape", "jalal-sons", url=[JALAL_URL, JALAL_URL], stdout=StringIO())
        self.assertEqual(RetailerListing.objects.filter(is_demo=False).count(), 1)
        self.assertEqual(PriceHistory.objects.count(), 2)
        self.assertEqual(ScrapeRun.objects.filter(status="success", products_collected=1).count(), 2)
        self.assertEqual(client_class.return_value.get_html.call_count, 2)

    @override_settings(SCRAPING_ENABLED=True)
    def test_partial_failure_keeps_completed_observation_and_audits_error(self):
        call_command("seed_retailers", stdout=StringIO())
        Retailer.objects.filter(slug="jalal-sons").update(status="enabled", collection_enabled=True)
        with patch("catalog.management.commands.scrape.PoliteClient") as client_class:
            client_class.return_value.get_html.side_effect = [JALAL_HTML, CollectionError("HTTP 429; stopped")]
            with self.assertRaises(CommandError):
                call_command("scrape", "jalal-sons", url=[JALAL_URL, "https://www.jalalsons.com.pk/product/another-product-123456"], stdout=StringIO())
        run = ScrapeRun.objects.get()
        self.assertEqual(run.status, "partial")
        self.assertEqual(run.products_collected, 1)
        self.assertEqual(RetailerListing.objects.count(), 1)
        client_class.return_value.close.assert_called_once()
