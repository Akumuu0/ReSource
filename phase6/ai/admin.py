from django.contrib import admin

from .models import AIOutput


@admin.register(AIOutput)
class AIOutputAdmin(admin.ModelAdmin):
    """Lets the Administrator audit every AI call: the feature, whether the AI or the fallback answered,
    the confidence, and what the person decided."""

    list_display = ["id", "feature", "source", "confidence", "human_decision", "created_at"]
    list_filter = ["feature", "source"]
