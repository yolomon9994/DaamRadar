from django.contrib import admin
from django.urls import include, path
from .health import health

urlpatterns = [path("health/", health, name="health"), path("admin/", admin.site.urls), path("api/", include("catalog.api.urls")), path("", include("catalog.urls"))]
