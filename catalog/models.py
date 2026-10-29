from datetime import timedelta
from decimal import Decimal
import re
from urllib.parse import urlparse

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator, URLValidator
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.utils import timezone


class Retailer(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Under review"
        ENABLED = "enabled", "Validated"
        UNAVAILABLE = "unavailable", "Unavailable"

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    website = models.URLField()
    logo = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    collection_enabled = models.BooleanField(default=False)
    access_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=20, default="basket")

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class Product(models.Model):
    canonical_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True)
    brand = models.CharField(max_length=100, blank=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    quantity = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(Decimal("0.001"))])
    unit = models.CharField(max_length=10, blank=True, help_text="Normalized base unit: ml, g, or pc.")
    pack_count = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)])
    variant = models.CharField(max_length=120, blank=True)
    packaging = models.CharField(max_length=40, blank=True)
    gtin = models.CharField(max_length=14, blank=True, db_index=True)
    image = models.URLField(blank=True)
    illustration = models.CharField(max_length=30, default="basket")
    is_demo = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["canonical_name"]
        constraints = [models.CheckConstraint(condition=models.Q(pack_count__gte=1), name="product_positive_pack"),
                       models.CheckConstraint(condition=models.Q(quantity__isnull=True) | models.Q(quantity__gt=0), name="product_positive_quantity")]

    def __str__(self):
        return self.canonical_name

    @property
    def size_label(self):
        if self.quantity is None:
            return "Size unspecified"
        quantity, unit = self.quantity, self.unit
        if unit in {"ml", "g"} and quantity >= 1000:
            quantity, unit = quantity / 1000, {"ml": "L", "g": "kg"}[unit]
        label = f"{quantity.normalize():f} {unit}"
        return f"{self.pack_count} × {label}" if self.pack_count > 1 else label


class RetailerListing(models.Model):
    class Availability(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        OUT_OF_STOCK = "out_of_stock", "Out of stock"
        UNKNOWN = "unknown", "Availability unknown"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="listings")
    retailer = models.ForeignKey(Retailer, on_delete=models.PROTECT, related_name="listings")
    external_id = models.CharField(max_length=200)
    original_title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000, blank=True)
    current_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="PKR")
    availability = models.CharField(max_length=20, choices=Availability.choices, default=Availability.UNKNOWN)
    last_checked = models.DateTimeField(default=timezone.now)
    delivery_area = models.CharField(max_length=200, blank=True)
    delivery_area_key = models.SlugField(max_length=100, blank=True, validators=[RegexValidator(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "Use lowercase words or numbers separated by hyphens.")], help_text="Shared identifier for exactly the same delivery scope across retailers; a city name alone is not proof.")
    area_evidence_url = models.URLField(max_length=1000, blank=True, help_text="Public retailer evidence tying this listing's price and stock to this exact area at its check time. General delivery advertising is insufficient.")
    area_verified_at = models.DateTimeField(null=True, blank=True, help_text="When this observation's area was verified; must be on or after its last check. A new import clears verification.")
    is_demo = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["current_price", "retailer__name"]
        constraints = [models.UniqueConstraint(fields=["retailer", "external_id", "delivery_area", "is_demo"], name="unique_retailer_listing"),
                       models.CheckConstraint(condition=models.Q(current_price__gt=0), name="positive_listing_price"),
                       models.CheckConstraint(condition=models.Q(currency="PKR"), name="listing_pkr_only"),
                       models.CheckConstraint(condition=(
                           models.Q(delivery_area_key="", area_evidence_url="", area_verified_at__isnull=True)
                           | (models.Q(is_demo=False, area_verified_at__isnull=False)
                              & ~models.Q(delivery_area="") & ~models.Q(delivery_area_key="")
                              & ~models.Q(area_evidence_url=""))), name="complete_listing_area_evidence")]
        indexes = [models.Index(fields=["product", "current_price"])]

    @property
    def is_stale(self):
        return self.last_checked < timezone.now() - timedelta(hours=settings.PRICE_STALE_HOURS)

    @property
    def area_is_verified(self):
        """Verification belongs to an observation, never merely to a matching label."""
        if self.is_demo or not self.retailer_id or not self.last_checked or not all((self.delivery_area and self.delivery_area.strip(), self.delivery_area_key, self.area_evidence_url, self.area_verified_at)):
            return False
        if re.search(r"\b(unverified|unspecified|unknown)\b", self.delivery_area, re.I) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.delivery_area_key):
            return False
        try:
            URLValidator(schemes=["https"])(self.area_evidence_url)
            evidence, origin = urlparse(self.area_evidence_url), urlparse(self.retailer.website)
            return (evidence.netloc == origin.netloc
                    and not evidence.username and not evidence.password and not evidence.fragment
                    and self.last_checked <= self.area_verified_at <= timezone.now())
        except (ObjectDoesNotExist, ValidationError, ValueError, TypeError):
            return False

    def clean(self):
        super().clean()
        supplied = any((self.delivery_area_key, self.area_evidence_url, self.area_verified_at))
        if supplied and not self.area_is_verified:
            raise ValidationError("Area verification requires a delivery area, a shared scope key, a public HTTPS evidence URL on this retailer's origin, and a verification time between the observation's last check and now. Demo records cannot be verified.")

    def __str__(self):
        return f"{self.retailer}: {self.original_title}"


class PriceHistory(models.Model):
    listing = models.ForeignKey(RetailerListing, on_delete=models.CASCADE, related_name="history")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    checked_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-checked_at"]
        constraints = [models.CheckConstraint(condition=models.Q(price__gt=0), name="positive_history_price")]


class ScrapeRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"
        BLOCKED = "blocked", "Blocked"

    retailer = models.ForeignKey(Retailer, on_delete=models.PROTECT, related_name="scrape_runs")
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    products_collected = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    request_count = models.PositiveIntegerField(default=0)
    results = models.JSONField(default=list, blank=True, help_text="Requested URLs and their stored, failed, or pending outcomes.")

    class Meta:
        ordering = ["-started_at"]
        constraints = [models.UniqueConstraint(fields=["retailer"], condition=models.Q(status="running"), name="one_running_scrape_per_retailer")]


class AdminPriceRefresh(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Completed"
        PARTIAL = "partial", "Completed with errors"
        FAILED = "failed", "Failed"
        STOPPED = "stopped", "Stopped by operator"

    singleton = models.PositiveSmallIntegerField(default=1, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    sources = models.JSONField(default=list)
    results = models.JSONField(default=list)
    error = models.TextField(blank=True)
    worker_pid = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        permissions = [("run_price_refresh", "Can manually refresh reviewed prices")]
        constraints = [
            models.CheckConstraint(condition=models.Q(singleton=1), name="admin_refresh_singleton"),
            models.UniqueConstraint(fields=["singleton"], condition=models.Q(status__in=["queued", "running"]),
                                    name="one_active_admin_refresh"),
        ]

    @property
    def is_active(self):
        return self.status in {self.Status.QUEUED, self.Status.RUNNING}
