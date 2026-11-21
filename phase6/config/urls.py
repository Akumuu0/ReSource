"""Main URL list: each app has its own urls.py."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("assets/", include("assets.urls")),
    path("requests/", include("resource_requests.urls")),
]
