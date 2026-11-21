"""Accounts: departments, users with one role, and in-app notifications.

Class diagram: Department, User (Fig. 9-1) and Notification (Fig. 9-6).
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Department(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    campus = models.CharField(max_length=50)  # used by the matching "location" factor

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """A university user. Each user has exactly one role and one department."""

    REPRESENTATIVE = "DR"  # Department Representative (requester)
    COORDINATOR = "AC"     # Asset Coordinator (custodian)
    ADMINISTRATOR = "AD"   # Administrator (approver and admin)
    ROLE_CHOICES = [
        (REPRESENTATIVE, "Department Representative"),
        (COORDINATOR, "Asset Coordinator"),
        (ADMINISTRATOR, "Administrator"),
    ]

    # Default is the role with the fewest rights.
    role = models.CharField(max_length=2, choices=ROLE_CHOICES, default=REPRESENTATIVE)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, null=True, related_name="users")

    @property
    def is_representative(self):
        return self.role == self.REPRESENTATIVE

    @property
    def is_coordinator(self):
        return self.role == self.COORDINATOR

    @property
    def is_administrator(self):
        return self.role == self.ADMINISTRATOR

    def display_name(self):
        return self.get_full_name() or self.username


class Notification(models.Model):
    """An in-app message for one user (C8)."""

    REQUEST_MADE = "Request made"
    RELEASED = "Released"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    HANDED_OVER = "Handed over"
    RECEIVED = "Received"
    CANCELLED = "Cancelled"

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    event_type = models.CharField(max_length=30)
    message = models.CharField(max_length=255)
    link = models.CharField(max_length=200, blank=True)  # page the message is about
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_read(self):
        self.read_at = timezone.now()
        self.save(update_fields=["read_at"])
