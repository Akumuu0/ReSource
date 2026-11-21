"""AI records (design Fig. 9-4 and 9-5, tables AI_OUTPUT and RECOMMENDATION).

Every AI call - real or rule-based fallback - leaves one AIOutput row,
and later the human decision is added to it (FR-7.A4, AI-5).
A matching AIOutput also keeps its ranked candidates as Recommendation rows.
"""
import json

from django.conf import settings
from django.db import models
from django.utils import timezone

# The eight score factors of design Table 17-1, in the order the pages show them.
FACTOR_LABELS = {
    "function": "Function and specs",
    "quantity": "Quantity",
    "condition": "Condition",
    "location": "Location",
    "ready": "Ready by the date",
    "repair": "Repair cost",
    "transfer": "Transfer cost",
    "carbon": "Waste and carbon saved",
}


def confidence_level(confidence):
    """High, Medium or Low (design Table 4-2)."""
    if confidence is None:
        return "Unknown"
    if confidence >= 0.80:
        return "High"
    if confidence >= 0.50:
        return "Medium"
    return "Low"


class AIOutput(models.Model):
    CLASSIFICATION = "Classification"
    MATCHING = "Matching"
    REPORT = "Report"
    FEATURE_CHOICES = [(f, f) for f in [CLASSIFICATION, MATCHING, REPORT]]

    AI_SOURCE = "AI"
    FALLBACK_SOURCE = "AI unavailable, rule-based result"

    feature = models.CharField(max_length=20, choices=FEATURE_CHOICES)
    input_text = models.TextField()   # exactly what was (or would have been) sent, after removing personal data
    output_text = models.TextField()  # the result as JSON
    confidence = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=60)  # AI_SOURCE or FALLBACK_SOURCE
    note = models.CharField(max_length=255, blank=True)  # "OK", "No API key", "Timed out after 20 s", ...
    model_name = models.CharField(max_length=60, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    # Who started the call. Kept inside ReSource; never sent to the AI provider.
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    # The human decision, filled in later (accepted, edited, rejected, published...).
    human_decision = models.CharField(max_length=255, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "AI output"

    def __str__(self):
        return f"{self.feature} #{self.pk} ({self.source})"

    @property
    def used_ai(self):
        return self.source == self.AI_SOURCE

    @property
    def confidence_level(self):
        return confidence_level(self.confidence)

    def record_decision(self, user, decision):
        self.human_decision = decision[:255]
        self.decided_by = user
        self.decided_at = timezone.now()
        self.save(update_fields=["human_decision", "decided_by", "decided_at"])


class Recommendation(models.Model):
    """One ranked candidate of a matching AIOutput, with its explanation (design Fig. 9-5, Table 17-2)."""

    output = models.ForeignKey(AIOutput, on_delete=models.CASCADE, related_name="recommendations")
    # The request it was ranked for (ERD RECOMMENDATION.request_id). Empty for "Check listings",
    # which ranks a need that is not saved yet.
    request = models.ForeignKey("resource_requests.Request", on_delete=models.CASCADE, null=True, blank=True,
                                related_name="+")
    asset = models.ForeignKey("assets.Asset", on_delete=models.CASCADE, related_name="+")
    rank = models.PositiveSmallIntegerField()     # 1 = best
    score = models.PositiveSmallIntegerField()    # 0-100 (Section 17.1)
    confidence = models.FloatField()              # 0-1 (Section 17.2)
    factors = models.TextField()                  # the eight factor values as JSON
    reason = models.TextField()                   # "in plain words": the AI sentence or the template sentence
    strengths = models.CharField(max_length=255)  # the three strongest factors
    limitation = models.CharField(max_length=255) # the factor with the largest gap

    class Meta:
        ordering = ["output_id", "rank"]

    def __str__(self):
        return f"#{self.rank} {self.asset.code} ({self.score})"

    @property
    def confidence_level(self):
        return confidence_level(self.confidence)

    def factor_rows(self):
        """(label, value, percent) for the factor bars on the page."""
        values = json.loads(self.factors)
        return [(label, values[key], round(100 * values[key])) for key, label in FACTOR_LABELS.items()]

    def meets_quantity(self):
        return json.loads(self.factors)["quantity"] == 1
