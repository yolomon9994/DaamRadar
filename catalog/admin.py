from django.contrib import admin
from django import forms
from django.core.exceptions import PermissionDenied, ValidationError
from django.core import signing
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST, require_safe

from .models import AdminPriceRefresh, Category, PriceHistory, Product, Retailer, RetailerListing, ScrapeRun
from .services.collection_health import can_view_collection_health, collection_health
from .services.admin_refresh import can_start_refresh, launch_refresh, refresh_progress, validate_refresh, validate_worker_database
from .services.admin_refresh import can_start_import, validate_import
from .services.catalog_import import import_batch_choices, plan_import
from .management.commands.refresh_prices import REVIEWED_RETAILERS


class RefreshForm(forms.Form):
    source = forms.ChoiceField(label="Sources to refresh", choices=[
        ("both", "Jalal Sons, then Cartpk"), ("jalal-sons", "Jalal Sons only"), ("cartpk", "Cartpk only")])


class ImportBatchForm(forms.Form):
    batch = forms.ChoiceField(label="Reviewed batch", choices=import_batch_choices)


class ImportStartForm(ImportBatchForm):
    batch = forms.ChoiceField(choices=import_batch_choices, widget=forms.HiddenInput)
    preview_token = forms.CharField(max_length=10000, widget=forms.HiddenInput)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["canonical_name", "brand", "category", "is_demo"]
    list_filter = ["is_demo", "category"]
    search_fields = ["canonical_name", "brand", "gtin"]


class ProductSourceFilter(admin.SimpleListFilter):
    title = "product catalog"
    parameter_name = "product_source"

    def lookups(self, request, model_admin):
        return [("live", "Collected"), ("demo", "Demo")]

    def queryset(self, request, queryset):
        if self.value() in {"live", "demo"}:
            return queryset.filter(product__is_demo=self.value() == "demo")
        return queryset


@admin.register(RetailerListing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ["original_title", "retailer", "current_price", "availability", "last_checked", "area_is_verified", "is_demo"]
    list_filter = ["retailer", "is_demo", ProductSourceFilter, "availability"]
    search_fields = ["original_title"]
    list_select_related = ["retailer"]
    readonly_fields = ["area_is_verified"]
    fieldsets = [
        (None, {"fields": ["product", "retailer", "external_id", "original_title", "url", "current_price", "currency", "availability", "last_checked", "is_demo"]}),
        ("Delivery evidence", {"fields": ["delivery_area", "delivery_area_key", "area_evidence_url", "area_verified_at", "area_is_verified"],
                               "description": "Record evidence for this particular price/stock observation and exact delivery scope. Homepage delivery claims, store addresses and generic InStock markup are insufficient. Current collectors leave this unverified."}),
    ]

@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    list_display = ["id", "retailer", "status", "products_collected", "request_count", "error_code", "started_at"]
    list_filter = ["retailer", "status", "error_code"]
    readonly_fields = ["retailer", "started_at", "completed_at", "products_collected", "request_count", "error_code", "error", "results"]
    list_select_related = ["retailer"]

    def has_add_permission(self, request):
        return False

@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "collection_enabled"]
    list_filter = ["status", "collection_enabled"]
    change_list_template = "admin/catalog/retailer/change_list.html"

    def get_urls(self):
        return [path("collection-health/", self.admin_site.admin_view(self.collection_health),
                     name="catalog_collection_health"),
                path("collection-refresh/start/", self.admin_site.admin_view(self.start_refresh), name="catalog_refresh_start"),
                path("collection-refresh/<int:job_id>/", self.admin_site.admin_view(self.refresh_detail), name="catalog_refresh_detail"),
                path("collection-refresh/<int:job_id>/status/", self.admin_site.admin_view(self.refresh_status), name="catalog_refresh_status"),
                path("collection-import/", self.admin_site.admin_view(self.import_preview), name="catalog_import_preview"),
                path("collection-import/start/", self.admin_site.admin_view(self.start_import), name="catalog_import_start"),
                ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        return super().changelist_view(request, {**(extra_context or {}),
                                               "can_view_collection_health": can_view_collection_health(request.user)})

    @method_decorator(require_safe)
    def collection_health(self, request):
        if not can_view_collection_health(request.user):
            raise PermissionDenied
        form = forms.Form(request.GET)
        form.fields["retailer"] = forms.ChoiceField(required=False, label="Retailer",
            choices=[("", "All retailers"), *Retailer.objects.order_by("name").values_list("slug", "name")])
        valid = form.is_valid()
        health = collection_health(retailer_slug=form.cleaned_data["retailer"]) if valid else {}
        page = Paginator(health.pop("stale_listings"), 25).get_page(request.GET.get("page")) if valid else None
        context = {**self.admin_site.each_context(request), **health, "title": "Collection health",
                   "opts": self.model._meta, "filter_form": form, "page_obj": page,
                   "can_start_refresh": can_start_refresh(request.user), "refresh_form": RefreshForm(),
                   "active_refresh": AdminPriceRefresh.objects.filter(status__in=["queued", "running"]).first(),
                   "recent_refreshes": AdminPriceRefresh.objects.order_by("-created_at", "-pk")[:10],
                   "retailer_slug": form.cleaned_data.get("retailer", ""), "valid_filter": valid}
        return TemplateResponse(request, "admin/catalog/collection_health.html", context, status=200 if valid else 400)

    @method_decorator(require_POST)
    def start_refresh(self, request):
        if not can_start_refresh(request.user):
            raise PermissionDenied
        form = RefreshForm(request.POST)
        active = None
        status = 400
        if form.is_valid():
            selected = form.cleaned_data["source"]
            sources = list(REVIEWED_RETAILERS) if selected == "both" else [selected]
            try:
                validate_worker_database()
                validate_refresh(sources)
                with transaction.atomic():
                    job = AdminPriceRefresh.objects.create(requested_by=request.user, sources=sources, results=[
                        {"retailer": source, "outcome": "not_attempted", "run_id": None, "run_status": None,
                         "products_collected": 0, "request_count": 0, "error": ""} for source in sources])
                    transaction.on_commit(lambda: launch_refresh(job.pk))
                return redirect("admin:catalog_refresh_detail", job_id=job.pk)
            except ValidationError as exc:
                form.add_error(None, exc)
            except IntegrityError:
                active = AdminPriceRefresh.objects.filter(status__in=["queued", "running"]).first()
                if active is None:
                    raise
                form.add_error(None, "Another admin refresh is already queued or running. Open its progress; no duplicate was started.")
                status = 409
        context = {**self.admin_site.each_context(request), "title": "Start price refresh", "opts": self.model._meta,
                   "refresh_form": form, "active_refresh": active}
        return TemplateResponse(request, "admin/catalog/refresh_start.html", context, status=status)

    def get_refresh(self, request, job_id):
        if not can_view_collection_health(request.user):
            raise PermissionDenied
        return get_object_or_404(AdminPriceRefresh, pk=job_id)

    def import_context(self, request, form, key=None, errors=None):
        plan, setup_errors, start_form = None, [], None
        active = AdminPriceRefresh.objects.filter(status__in=["queued", "running"]).first()
        if key:
            try:
                plan = plan_import(key)
                try:
                    validate_import(key)
                except ValidationError as exc:
                    setup_errors = exc.messages
                token = signing.dumps({"user_id": request.user.pk, "batch": key, "urls": plan["missing_urls"]},
                                      salt="catalog-admin-import")
                start_form = ImportStartForm(initial={"batch": key, "preview_token": token})
            except ValidationError as exc:
                setup_errors = exc.messages
        return {**self.admin_site.each_context(request), "title": "Import reviewed catalog", "opts": self.model._meta,
                "batch_form": form, "start_form": start_form, "plan": plan, "setup_errors": setup_errors,
                "import_errors": errors or [], "can_start_import": can_start_import(request.user), "active_refresh": active}

    @method_decorator(require_safe)
    def import_preview(self, request):
        if not can_view_collection_health(request.user):
            raise PermissionDenied
        form = ImportBatchForm(request.GET or None)
        valid = form.is_bound and form.is_valid()
        context = self.import_context(request, form, form.cleaned_data["batch"] if valid else None)
        return TemplateResponse(request, "admin/catalog/import_preview.html", context,
                                status=400 if form.is_bound and not valid else 200)

    @method_decorator(require_POST)
    def start_import(self, request):
        if not can_start_import(request.user):
            raise PermissionDenied
        form = ImportStartForm(request.POST)
        key, errors, status = None, [], 400
        if form.is_valid():
            key = form.cleaned_data["batch"]
            try:
                payload = signing.loads(form.cleaned_data["preview_token"], salt="catalog-admin-import", max_age=900)
                plan = plan_import(key)
                if payload.get("user_id") != request.user.pk or payload.get("batch") != key:
                    raise ValidationError("This preview belongs to another account or batch. Preview the batch again.")
                if payload.get("urls") != plan["missing_urls"]:
                    raise ValidationError("The missing listings changed since preview. Preview the batch again before importing.")
                if not plan["missing_urls"]:
                    raise ValidationError("This batch has no missing listings. Nothing was queued.")
                validate_worker_database()
                validate_import(key, plan["missing_urls"])
                with transaction.atomic():
                    job = AdminPriceRefresh.objects.create(requested_by=request.user, kind="import", batch=key,
                        targets=plan["missing_urls"], sources=[plan["source"]], results=[{
                            "retailer": plan["source"], "outcome": "not_attempted", "run_id": None,
                            "run_status": None, "products_collected": 0, "request_count": 0, "error": ""}])
                    transaction.on_commit(lambda: launch_refresh(job.pk))
                return redirect("admin:catalog_refresh_detail", job_id=job.pk)
            except signing.BadSignature:
                errors = ["The preview is invalid or expired. Preview the batch again before importing."]
            except ValidationError as exc:
                errors = exc.messages
            except IntegrityError:
                if not AdminPriceRefresh.objects.filter(status__in=["queued", "running"]).exists():
                    raise
                errors, status = ["Another import or refresh is active. Open its progress; no duplicate was started."], 409
        else:
            errors = ["Choose a valid reviewed batch and preview it before importing."]
        batch_form = ImportBatchForm({"batch": key}) if key else ImportBatchForm()
        return TemplateResponse(request, "admin/catalog/import_preview.html",
                                self.import_context(request, batch_form, key, errors), status=status)

    @method_decorator(require_safe)
    def refresh_detail(self, request, job_id):
        job = self.get_refresh(request, job_id)
        return TemplateResponse(request, "admin/catalog/refresh_detail.html", {
            **self.admin_site.each_context(request), "title": f"{job.get_kind_display()} #{job.pk}", "opts": self.model._meta,
            "job": job, "progress": refresh_progress(job),
        })

    @method_decorator(require_safe)
    def refresh_status(self, request, job_id):
        return JsonResponse(refresh_progress(self.get_refresh(request, job_id)))


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ["id", "listing", "price", "checked_at"]
    list_select_related = ["listing", "listing__retailer"]
    readonly_fields = ["listing", "price", "checked_at", "context"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Category)
admin.site.site_header = "DaamRadar administration"
