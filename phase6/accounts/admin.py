from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Department, Notification, User


@admin.register(User)
class ReSourceUserAdmin(UserAdmin):
    # Show and edit our two extra fields: role and department.
    list_display = ["username", "first_name", "last_name", "role", "department", "is_active"]
    list_filter = ["role", "department"]
    fieldsets = UserAdmin.fieldsets + (("ReSource", {"fields": ("role", "department")}),)


admin.site.register(Department)
admin.site.register(Notification)
