from django.contrib import admin

from .models import Approval, Request, Transfer


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = ["code", "requester", "department", "asset", "quantity", "state"]
    list_filter = ["state", "department"]


admin.site.register(Approval)
admin.site.register(Transfer)
