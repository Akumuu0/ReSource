"""Assets: categories, assets and their life-cycle history.

Class diagram: Category and Asset (Fig. 9-1), LifecycleEvent (Fig. 9-3).
"""
from django.conf import settings
from django.db import models

from accounts.models import Department


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    # Words that point to this category. Used by the rule-based classifier
    # when the AI is not available.
    keywords = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name

    def keyword_list(self):
        return [word.strip().lower() for word in self.keywords.split(",") if word.strip()]


class Asset(models.Model):
    # States (subset of the state diagram, design Fig. 12-1)
    DRAFT = "Draft"
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    IN_TRANSFER = "In Transfer"
    IN_USE = "In Use"
    WITHDRAWN = "Withdrawn"
    STATE_CHOICES = [(s, s) for s in [DRAFT, AVAILABLE, RESERVED, IN_TRANSFER, IN_USE, WITHDRAWN]]

    CONDITION_CHOICES = [("New", "New"), ("Good", "Good"), ("Fair", "Fair"), ("Poor", "Poor")]

    code = models.CharField(max_length=20, unique=True)  # e.g. A-2026-0412
    name = models.CharField(max_length=120)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="assets")
    condition = models.CharField(max_length=4, choices=CONDITION_CHOICES)
    tags = models.CharField(max_length=200, blank=True)  # comma-separated
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="assets")  # owner
    quantity = models.PositiveIntegerField()               # units this record holds
    available_quantity = models.PositiveIntegerField(default=0)  # units free to reserve
    estimated_value = models.DecimalField(max_digits=10, decimal_places=2)  # AED per unit
    weight_kg = models.DecimalField(max_digits=8, decimal_places=2)         # kg per unit
    repair_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # expected repair, AED per unit
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=DRAFT)
    # When some units are reserved, they get their own record that points back here.
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="parts")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"

    def tag_list(self):
        return [tag.strip() for tag in self.tags.split(",") if tag.strip()]

    def is_visible_to(self, user):
        """Drafts are visible only to their own department and to Administrators."""
        if self.state != self.DRAFT:
            return True
        return user.is_administrator or user.department_id == self.department_id


class LifecycleEvent(models.Model):
    """One line of an asset's history: who did what, when, old and new state."""

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="events")
    action = models.CharField(max_length=60)
    old_state = models.CharField(max_length=20, blank=True)
    new_state = models.CharField(max_length=20)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    occurred_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["occurred_at", "id"]

    def save(self, *args, **kwargs):
        # History is never changed after it is written (design FR-5.18).
        if self.pk:
            raise ValueError("Life-cycle events cannot be edited.")
        super().save(*args, **kwargs)
