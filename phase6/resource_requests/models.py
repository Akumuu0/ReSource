"""Requests, approvals and transfers.

Class diagram: Request (Fig. 9-1), Approval and Transfer (Fig. 9-2).
States follow Fig. 12-3 (Request) and Fig. 12-4 (Approval and Transfer), subset for the draft.
"""
from django.conf import settings
from django.db import models

from accounts.models import Department
from assets.models import Asset, Category


class Request(models.Model):
    OPEN = "Open"                # a need without an asset yet (waiting for a match)
    SUBMITTED = "Submitted"      # waiting for the owning Asset Coordinator
    RELEASED = "Released"        # waiting for an Administrator
    APPROVED = "Approved"        # units reserved, waiting for hand-over
    IN_TRANSFER = "In Transfer"  # handed over, waiting for receipt
    COMPLETED = "Completed"
    REJECTED = "Rejected"
    CANCELLED = "Cancelled"
    STATE_CHOICES = [(s, s) for s in [OPEN, SUBMITTED, RELEASED, APPROVED, IN_TRANSFER, COMPLETED, REJECTED, CANCELLED]]
    FINISHED_STATES = [COMPLETED, REJECTED, CANCELLED]

    LOW, MEDIUM, HIGH = "Low", "Medium", "High"
    URGENCY_CHOICES = [(u, u) for u in [LOW, MEDIUM, HIGH]]

    code = models.CharField(max_length=20, unique=True)  # e.g. R-2026-0391
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requests_made")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="requests")  # requesting dept
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True, related_name="requests")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, null=True, blank=True)  # for open needs
    quantity = models.PositiveIntegerField()
    purpose = models.TextField()
    needed_by = models.DateField()
    # Used to rank matches for an open need (design 7.2 and Section 17).
    specifications = models.CharField(max_length=200, blank=True)  # minimums, e.g. "At least 70 MHz, 2 channels"
    min_condition = models.CharField(max_length=4, choices=Asset.CONDITION_CHOICES, blank=True)
    urgency = models.CharField(max_length=6, choices=URGENCY_CHOICES, default=MEDIUM)
    # The AI recommendation the requester chose, shown again to the approvers (design 7.4).
    recommendation = models.ForeignKey("ai.Recommendation", on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name="+")
    state = models.CharField(max_length=20, choices=STATE_CHOICES)
    reason = models.CharField(max_length=255, blank=True)  # why it was declined, rejected or cancelled
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.code

    def get_transfer(self):
        """The transfer of this request, or None if it was not approved."""
        return getattr(self, "transfer", None)

    @property
    def owner_department(self):
        """The department that owned the asset when it was requested (None for an open need)."""
        transfer = self.get_transfer()
        if transfer:
            return transfer.from_department  # the asset's department changes after receipt
        return self.asset.department if self.asset else None

    @property
    def estimated_value(self):
        """Value of the requested units in AED: quantity x value per unit (None for an open need)."""
        return self.quantity * self.asset.estimated_value if self.asset else None

    def is_finished(self):
        return self.state in self.FINISHED_STATES

    PROGRESS_STEPS = [(SUBMITTED, "Submitted"), (RELEASED, "Released"), (APPROVED, "Approved"),
                      (IN_TRANSFER, "Handed over"), (COMPLETED, "Received")]

    def progress(self):
        """Steps for the progress bar on the request page, as (label, done)."""
        states = [state for state, label in self.PROGRESS_STEPS]
        reached = states.index(self.state) if self.state in states else -1
        return [(label, index <= reached) for index, (state, label) in enumerate(self.PROGRESS_STEPS)]

    def is_visible_to(self, user):
        """People of the two departments involved, and Administrators."""
        if user.is_administrator or user.department_id == self.department_id:
            return True
        owner = self.owner_department
        return owner is not None and user.department_id == owner.id


class Approval(models.Model):
    """One decision on a request: the release or the approval."""

    RELEASE = "Release"    # by the owning Asset Coordinator
    APPROVAL = "Approval"  # by an Administrator
    APPROVED = "Approved"
    REJECTED = "Rejected"

    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="approvals")
    step = models.CharField(max_length=10, choices=[(RELEASE, RELEASE), (APPROVAL, APPROVAL)])
    decision = models.CharField(max_length=10, choices=[(APPROVED, APPROVED), (REJECTED, REJECTED)])
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=255, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["decided_at", "id"]

    def is_by(self, user):
        """True if this user made this decision (used to stop self-approval, FR-4.4)."""
        return self.decided_by_id == user.id


class Transfer(models.Model):
    """Moving the reserved units from the owning to the requesting department."""

    SCHEDULED = "Scheduled"
    IN_TRANSFER = "In Transfer"
    RECEIVED = "Received"
    CANCELLED = "Cancelled"
    STATE_CHOICES = [(s, s) for s in [SCHEDULED, IN_TRANSFER, RECEIVED, CANCELLED]]

    request = models.OneToOneField(Request, on_delete=models.CASCADE, related_name="transfer")
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="transfers")  # the reserved units
    quantity = models.PositiveIntegerField()
    from_department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="+")
    to_department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)
    handed_over_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    handed_over_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    received_at = models.DateTimeField(null=True, blank=True)
    condition_on_arrival = models.CharField(max_length=4, choices=Asset.CONDITION_CHOICES, blank=True)

    def __str__(self):
        return f"Transfer for {self.request.code}"
