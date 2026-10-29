"""Read-only batch planning and existing-listing checks for missing-only imports."""
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.db.models import Q

from catalog.models import Retailer, RetailerListing
from catalog.scraping.adapters import ADAPTERS
from catalog.scraping.batches import BATCHES, reviewed_urls
from catalog.scraping.reviewed import REVIEWED_BY_SOURCE
from catalog.scraping.types import CollectionError

SUPPORTED_SOURCES = ("jalal-sons", "cartpk")


def import_batch_choices():
    names = {"jalal-sons": "Jalal Sons", "cartpk": "Cartpk"}
    return [(key, f"{names[batch['retailer']]} — {key.removeprefix(batch['retailer'] + '-').replace('-', ' ').capitalize()} ({len(batch['urls'])} products)")
            for key, batch in BATCHES.items() if batch["retailer"] in SUPPORTED_SOURCES]


def get_import_batch(key):
    batch = BATCHES.get(key)
    if not batch or batch["retailer"] not in SUPPORTED_SOURCES:
        raise ValidationError("Choose a saved reviewed batch from Jalal Sons or Cartpk.")
    urls = list(dict.fromkeys(batch["urls"]))
    if not urls or len(urls) > 10:
        raise ValidationError("A reviewed import batch must contain one to ten distinct product URLs.")
    adapter = ADAPTERS[batch["retailer"]]()
    for url in urls:
        try:
            adapter.validate_url(url)
        except CollectionError as exc:
            raise ValidationError(str(exc)) from None
        if url not in reviewed_urls(batch["retailer"]):
            raise ValidationError("The batch contains a URL outside the saved reviewed catalog.")
    return batch, urls


def import_existing(retailer, urls):
    """An existing non-demo record blocks reimport regardless of age, stock or area."""
    identifiers = [urlparse(url).path.strip("/") for url in urls]
    return RetailerListing.objects.filter(retailer=retailer, is_demo=False).filter(
        Q(url__in=urls) | Q(external_id__in=identifiers))


def missing_import_urls(retailer, urls):
    records = list(import_existing(retailer, urls))
    saved_urls = {record.url for record in records}
    saved_ids = {record.external_id for record in records}
    return [url for url in urls if url not in saved_urls and urlparse(url).path.strip("/") not in saved_ids]


def plan_import(key):
    batch, urls = get_import_batch(key)
    retailer = Retailer.objects.filter(slug=batch["retailer"]).first()
    missing = set(missing_import_urls(retailer, urls)) if retailer else set(urls)
    rows = [{"url": url, "title": REVIEWED_BY_SOURCE[batch["retailer"]].get(urlparse(url).path, {}).get(
                "title", "Reviewed product — see source URL"), "missing": url in missing} for url in urls]
    return {"batch_key": key, "source": batch["retailer"], "retailer": retailer,
            "reviewed_at": batch["reviewed_at"], "rows": rows,
            "missing_urls": [url for url in urls if url in missing],
            "missing_count": len(missing), "existing_count": len(urls) - len(missing)}
