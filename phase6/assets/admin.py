from django.contrib import admin

from .models import Asset, Category, LifecycleEvent


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "category", "department", "state", "quantity", "available_quantity"]
    list_filter = ["state", "category", "department"]


admin.site.register(Category)
admin.site.register(LifecycleEvent)
