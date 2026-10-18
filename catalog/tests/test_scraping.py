from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from catalog.models import Retailer, ScrapeRun
from catalog.scraping.adapters import AlFatahAdapter
from catalog.scraping.client import PoliteClient
from catalog.scraping.parsers import parse_product_html
from catalog.scraping.types import CollectionError

HTML = (Path(__file__).parent / "fixtures" / "product.html").read_text(encoding="utf-8")


class ParserTests(SimpleTestCase):
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
