from django.contrib import admin
from django.urls import include, path

urlpatterns = [path("admin/", admin.site.urls), path("api/", include("catalog.api.urls")), path("", include("catalog.urls"))]
