from django.contrib import admin

from .models import AIOutput


@admin.register(AIOutput)
class AIOutputAdmin(admin.ModelAdmin):
    list_display = ["id", "feature", "source", "confidence", "human_decision", "created_at"]
    list_filter = ["feature", "source"]
