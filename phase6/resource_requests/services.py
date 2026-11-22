"""Request, approval and transfer rules.

Design: Requests and Reservations, Approvals and Transfers modules (Table 16-1),
sequence diagrams 10.1 (release and approve) and 10.2 (transfer).
Every method checks the user's role and department first, then the request state.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.common import BusinessRuleError, next_code
from accounts.models import Notification, User
from accounts.permissions import require_department, require_role
from accounts.services import NotificationService
from assets.models import Asset
from assets.services import AssetService

from .models import Approval, Request, Transfer


def link_to(request):
    return reverse("request_detail", args=[request.pk])


def require_reason(reason):
    reason = (reason or "").strip()
    if not reason:
        raise BusinessRuleError("A reason is required.")
    return reason


class RequestService:
    """C4: submit requests and needs, choose a match, cancel, list."""

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
    @transaction.atomic
    def submit_need(user, category, quantity, purpose, needed_by, specifications="", min_condition="",
                    urgency=Request.MEDIUM, code=None):
        """Describe a need without choosing an asset. It stays Open until a match is chosen."""
        require_role(user, User.REPRESENTATIVE)
        if quantity < 1:
            raise BusinessRuleError("Quantity must be at least 1.")
        RequestService.check_date(needed_by)
        return Request.objects.create(
            code=code or next_code(Request, "R"),
            requester=user,
            department=user.department,
            category=category,
            quantity=quantity,
            purpose=purpose,
            needed_by=needed_by,
            specifications=specifications,
            min_condition=min_condition,
            urgency=urgency,
            state=Request.OPEN,
        )

    @staticmethod
    def notify_new_request(request):
        NotificationService.notify(
            NotificationService.coordinators_of(request.asset.department),
            Notification.REQUEST_MADE,
            f"New request {request.code}: {request.quantity} x {request.asset.name} for {request.department}.",
            link_to(request),
        )

    # --- AI-2: the requester's decision on the matches ------------------------

    @staticmethod
    @transaction.atomic
    def choose_match(user, request, asset, recommendation=None, reason=""):
        """The requester accepts one match; the request then goes to that asset's coordinator.

        Choosing anything other than the top recommendation needs a reason (FR-8.7).
        """
        RequestService.require_requester(user, request)
        RequestService.require_state(request, Request.OPEN)
        if recommendation and recommendation.request_id != request.pk:
            raise BusinessRuleError("This recommendation was made for another request.")
        if recommendation and recommendation.rank > 1:
            if not (reason or "").strip():
                raise BusinessRuleError("Choosing another asset than the top match needs a reason.")
        RequestService.check_not_own(user, asset)
        RequestService.check_units(asset, request.quantity)  # recheck: the list may be out of date
        request.asset = asset
        request.recommendation = recommendation
        request.state = Request.SUBMITTED
        request.save()
        RequestService.notify_new_request(request)

    @staticmethod
    @transaction.atomic
    def reject_matches(user, request, reason):
        """The requester rejects all matches; the need is closed with the reason."""
        RequestService.require_requester(user, request)
        RequestService.require_state(request, Request.OPEN)
        request.reason = f"No suitable match: {require_reason(reason)}"
        request.state = Request.CANCELLED
        request.save()

    # --- cancel ---------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def cancel(user, request, reason=""):
        """The requester cancels before hand-over. Reserved units go back on offer."""
        RequestService.require_requester(user, request)
        RequestService.require_state(request, Request.OPEN, Request.SUBMITTED, Request.RELEASED, Request.APPROVED)
        old_state = request.state
        if old_state == Request.APPROVED:
            transfer = request.transfer
            transfer.state = Transfer.CANCELLED
            transfer.save()
            AssetService.release_reservation(transfer.asset, user, request.code)
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


class ApprovalService:
    """C5: the owning Asset Coordinator releases, then an Administrator approves."""

    @staticmethod
    def check_not_involved(user, request):
        """Nobody may approve a request they submitted or released (FR-4.4, BR-4).

        We compare user IDs, not role names, so changing someone's role
        does not get around this rule.
        """
        if request.requester_id == user.id:
            raise BusinessRuleError(
                "You submitted this request, so you cannot approve or reject it. Another Administrator must decide."
            )
        if any(approval.is_by(user) for approval in request.approvals.all()):
            raise BusinessRuleError(
                "You released this request, so you cannot also approve or reject it. Another Administrator must decide."
            )

    @staticmethod
    @transaction.atomic
    def release(user, request):
        RequestService.require_state(request, Request.SUBMITTED)
        AssetService.require_owning_coordinator(user, request.asset)
        if request.requester_id == user.id:
            raise BusinessRuleError("You cannot release your own request.")
        Approval.objects.create(request=request, step=Approval.RELEASE, decision=Approval.APPROVED, decided_by=user)
        request.state = Request.RELEASED
        request.save()
        NotificationService.notify(
            [request.requester], Notification.RELEASED,
            f"{request.code} was released by {request.owner_department} and is waiting for approval.", link_to(request),
        )
        NotificationService.notify(
            NotificationService.administrators(), Notification.RELEASED,
            f"{request.code} was released and needs your approval.", link_to(request),
        )

    @staticmethod
    @transaction.atomic
    def decline(user, request, reason):
        RequestService.require_state(request, Request.SUBMITTED)
        AssetService.require_owning_coordinator(user, request.asset)
        reason = require_reason(reason)
        Approval.objects.create(request=request, step=Approval.RELEASE, decision=Approval.REJECTED,
                                decided_by=user, reason=reason)
        request.state = Request.REJECTED
        request.reason = reason
        request.save()
        NotificationService.notify(
            [request.requester], Notification.REJECTED,
            f"{request.code} was declined: {reason}", link_to(request),
        )

    @staticmethod
    @transaction.atomic
    def approve(user, request):
        """Final approval. Reserving the units and saving the approval happen in ONE transaction:
        if the units are gone, nothing is saved."""
        require_role(user, User.ADMINISTRATOR)
        RequestService.require_state(request, Request.RELEASED)
        ApprovalService.check_not_involved(user, request)

        reserved_asset = AssetService.reserve_units(request.asset, request.quantity, user, request.code)
        Approval.objects.create(request=request, step=Approval.APPROVAL, decision=Approval.APPROVED, decided_by=user)
        Transfer.objects.create(
            request=request,
            asset=reserved_asset,
            quantity=request.quantity,
            from_department=request.asset.department,
            to_department=request.department,
        )
        request.state = Request.APPROVED
        request.save()
        NotificationService.notify(
            [request.requester] + NotificationService.coordinators_of(request.owner_department),
            Notification.APPROVED,
            f"{request.code} was approved. {request.quantity} units are reserved and waiting for hand-over.",
            link_to(request),
        )

    @staticmethod
    @transaction.atomic
    def reject(user, request, reason):
        require_role(user, User.ADMINISTRATOR)
        RequestService.require_state(request, Request.RELEASED)
        ApprovalService.check_not_involved(user, request)
        reason = require_reason(reason)
        Approval.objects.create(request=request, step=Approval.APPROVAL, decision=Approval.REJECTED,
                                decided_by=user, reason=reason)
        request.state = Request.REJECTED
        request.reason = reason
        request.save()
        NotificationService.notify(
            [request.requester] + NotificationService.coordinators_of(request.owner_department),
            Notification.REJECTED,
            f"{request.code} was rejected: {reason}",
            link_to(request),
        )


class TransferService:
    """C5: hand-over by the owner, receipt by the receiver."""

    @staticmethod
    @transaction.atomic
    def hand_over(user, request):
        RequestService.require_state(request, Request.APPROVED)
        transfer = request.transfer
        AssetService.require_owning_coordinator(user, transfer.asset)
        AssetService.hand_over(transfer.asset, user, request.code)
        transfer.state = Transfer.IN_TRANSFER
        transfer.handed_over_by = user
        transfer.handed_over_at = timezone.now()
        transfer.save()
        request.state = Request.IN_TRANSFER
        request.save()
        NotificationService.notify(
            [request.requester], Notification.HANDED_OVER,
            f"{request.code} has been handed over. Please confirm receipt when it arrives.", link_to(request),
        )

    @staticmethod
    def require_receiver(user, request):
        """Only a Department Representative or Asset Coordinator of the receiving department (FR-4.10)."""
        require_role(user, User.REPRESENTATIVE, User.COORDINATOR)
        require_department(user, request.department, "Only the receiving department can confirm receipt.")

    @staticmethod
    @transaction.atomic
    def confirm_receipt(user, request, condition):
        RequestService.require_state(request, Request.IN_TRANSFER)
        TransferService.require_receiver(user, request)
        if condition not in dict(Asset.CONDITION_CHOICES):
            raise BusinessRuleError("Choose the condition on arrival.")
        transfer = request.transfer
        AssetService.complete_transfer(transfer.asset, user, request.department, condition, request.code)
        transfer.state = Transfer.RECEIVED
        transfer.received_by = user
        transfer.received_at = timezone.now()
        transfer.condition_on_arrival = condition
        transfer.save()
        request.state = Request.COMPLETED
        request.save()
        NotificationService.notify(
            NotificationService.coordinators_of(transfer.from_department) + NotificationService.administrators(),
            Notification.RECEIVED,
            f"{request.code} was received by {request.department} (condition: {condition}).",
            link_to(request),
        )
