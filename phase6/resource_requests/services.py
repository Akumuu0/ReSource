"""Request rules.

Design: Requests and Reservations module (Table 16-1).
Every method checks the user's role and department first, then the request state.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.common import BusinessRuleError, next_code
from accounts.models import Notification, User
from accounts.permissions import require_role
from accounts.services import NotificationService
from assets.models import Asset

from .models import Request


def link_to(request):
    return reverse("request_detail", args=[request.pk])


class RequestService:
    """C4: submit requests, cancel, list."""

    # --- checks ---------------------------------------------------------------

    @staticmethod
    def require_state(request, *states):
        if request.state not in states:
            raise BusinessRuleError(
                f"{request.code} is {request.state}; this action needs it to be {' or '.join(states)}."
            )

    @staticmethod
    def require_requester(user, request):
        require_role(user, User.REPRESENTATIVE)
        if request.requester_id != user.id:
            raise PermissionDenied("Only the person who made this request can do this.")

    @staticmethod
    def check_not_own(user, asset):
        """A department cannot request its own asset: the transfer would change nothing (C5)."""
        if asset.department_id == user.department_id:
            raise BusinessRuleError("This asset already belongs to your department.")

    @staticmethod
    def check_units(asset, quantity):
        if asset.state != Asset.AVAILABLE:
            raise BusinessRuleError(f"{asset.code} is not available (it is {asset.state}).")
        if quantity < 1:
            raise BusinessRuleError("Quantity must be at least 1.")
        if quantity > asset.available_quantity:
            raise BusinessRuleError(f"Only {asset.available_quantity} units of {asset.code} are available.")

    @staticmethod
    def check_date(needed_by):
        if needed_by < timezone.localdate():
            raise BusinessRuleError("The needed-by date cannot be in the past.")

    # --- submit ---------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def submit(user, asset, quantity, purpose, needed_by, code=None):
        """Request a listed asset. The request goes to the owning Asset Coordinator."""
        require_role(user, User.REPRESENTATIVE)
        RequestService.check_not_own(user, asset)
        RequestService.check_units(asset, quantity)
        RequestService.check_date(needed_by)
        request = Request.objects.create(
            code=code or next_code(Request, "R"),
            requester=user,
            department=user.department,  # always the requester's own department
            asset=asset,
            category=asset.category,
            quantity=quantity,
            purpose=purpose,
            needed_by=needed_by,
            state=Request.SUBMITTED,
        )
        RequestService.notify_new_request(request)
        return request

    @staticmethod
    def notify_new_request(request):
        NotificationService.notify(
            NotificationService.coordinators_of(request.asset.department),
            Notification.REQUEST_MADE,
            f"New request {request.code}: {request.quantity} x {request.asset.name} for {request.department}.",
            link_to(request),
        )

    # --- cancel ---------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def cancel(user, request, reason=""):
        """The requester cancels before hand-over. Reserved units go back on offer."""
        RequestService.require_requester(user, request)
        RequestService.require_state(request, Request.OPEN, Request.SUBMITTED, Request.RELEASED, Request.APPROVED)
        old_state = request.state
        request.state = Request.CANCELLED
        request.reason = (reason or "").strip() or "Cancelled by the requester."
        request.save()
        if old_state != Request.OPEN:
            NotificationService.notify(
                NotificationService.coordinators_of(request.owner_department),
                Notification.CANCELLED,
                f"{request.code} was cancelled by the requester.",
                link_to(request),
            )

    # --- lists ----------------------------------------------------------------

    @staticmethod
    def my_requests(user):
        return Request.objects.filter(requester=user).select_related("asset", "department")

    @staticmethod
    def tasks_for(user):
        """What is waiting for this user, as a list of (title, requests)."""
        if user.is_representative:
            return [
                ("Needs waiting for you to choose a match", Request.objects.filter(requester=user, state=Request.OPEN)),
                ("Arrived? Confirm receipt", Request.objects.filter(department=user.department, state=Request.IN_TRANSFER)),
            ]
        if user.is_coordinator:
            return [
                ("Release or decline", Request.objects.filter(state=Request.SUBMITTED, asset__department=user.department)),
                ("Hand over", Request.objects.filter(state=Request.APPROVED, transfer__from_department=user.department)),
                ("Arrived? Confirm receipt", Request.objects.filter(state=Request.IN_TRANSFER, department=user.department)),
            ]
        return [("Approve or reject", Request.objects.filter(state=Request.RELEASED))]
