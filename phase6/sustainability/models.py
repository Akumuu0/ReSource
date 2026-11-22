"""Sustainability values and reports.

Class diagram: CategoryValue and SustainabilityImpact (Fig. 9-6), AIReport (Fig. 9-5).
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from assets.models import Category

class CategoryValue(models.Model):
    """A versioned value for one category, with its source (FR-13.4, FR-13.5)."""

    EMISSION_FACTOR = "emission_factor"
    VALUE_TYPES = [(EMISSION_FACTOR, "Emission factor (kg CO2e per kg)")]

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="values")
    value_type = models.CharField(max_length=30, choices=VALUE_TYPES)
    value = models.DecimalField(max_digits=10, decimal_places=3)
    unit = models.CharField(max_length=30)
    source = models.CharField(max_length=200)
    effective_date = models.DateField()
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["category", "value_type", "-effective_date", "-version"]

    def __str__(self):
        return f"{self.category}: {self.value} {self.unit} (v{self.version})"

    @classmethod
    def emission_factor(cls, category):
        """The factor in force today for this category, or None if it has none (then FR-13.8 applies)."""
        current = cls.objects.filter(
            category=category, value_type=cls.EMISSION_FACTOR, effective_date__lte=timezone.localdate()
        ).order_by("-effective_date", "-version").first()
        return current.value if current else None


class AIReport(models.Model):
    """A generated summary: the AI drafts, the Administrator edits and publishes (AI-5)."""

    DRAFT = "Draft"
    PUBLISHED = "Published"
    DISCARDED = "Discarded"
    STATE_CHOICES = [(s, s) for s in [DRAFT, PUBLISHED, DISCARDED]]

    period_start = models.DateField()
    period_end = models.DateField()
    draft_text = models.TextField()   # what the AI (or the fallback) wrote; never changed
    final_text = models.TextField()   # what the Administrator edits and publishes
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=DRAFT)
    ai_output = models.ForeignKey("ai.AIOutput", on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"Summary {self.period_start:%d/%m/%Y}–{self.period_end:%d/%m/%Y} ({self.state})"


class SustainabilityImpact(models.Model):
    """One calculated figure, frozen with the report it belongs to (FR-13.5)."""

    report = models.ForeignKey(AIReport, on_delete=models.CASCADE, related_name="figures")
    period = models.CharField(max_length=30)  # e.g. "01/11/2026-30/11/2026"
    indicator = models.CharField(max_length=40)
    value = models.DecimalField(max_digits=14, decimal_places=2)
    unit = models.CharField(max_length=20)
    formula_version = models.CharField(max_length=20, default="draft-v1")

    class Meta:
        ordering = ["id"]
