from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
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
    is_demo = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["current_price", "retailer__name"]
        constraints = [models.UniqueConstraint(fields=["retailer", "external_id", "delivery_area", "is_demo"], name="unique_retailer_listing"),
                       models.CheckConstraint(condition=models.Q(current_price__gt=0), name="positive_listing_price"),
                       models.CheckConstraint(condition=models.Q(currency="PKR"), name="listing_pkr_only")]
        indexes = [models.Index(fields=["product", "current_price"])]

    @property
    def is_stale(self):
        return self.last_checked < timezone.now() - timedelta(hours=settings.PRICE_STALE_HOURS)

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
