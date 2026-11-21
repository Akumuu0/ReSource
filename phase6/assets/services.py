"""Asset business rules (design: Assets and Catalogue module, Table 16-1).

Views never change assets directly; they call these methods.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q

from accounts.common import BusinessRuleError, next_code
from accounts.models import User
from accounts.permissions import require_department, require_role

from .lifecycle import AssetStateMachine
from .models import Asset


class AssetService:

    # --- checks ---------------------------------------------------------------

    @staticmethod
    def require_owning_coordinator(user, asset):
        """Only the Asset Coordinator of the asset's own department may manage it."""
        require_role(user, User.COORDINATOR)
        require_department(user, asset.department, f"Only the Asset Coordinator of {asset.department} can do this.")

    @staticmethod
    def is_owning_coordinator(user, asset):
        try:
            AssetService.require_owning_coordinator(user, asset)
            return True
        except PermissionDenied:
            return False

    # --- C2: register and edit ------------------------------------------------

    @staticmethod
    @transaction.atomic
    def register(user, data, code=None):
        """Save a new asset as Draft in the coordinator's own department.

        data holds the form fields (name, description, category, condition,
        tags, quantity, estimated_value, weight_kg, repair_cost). `code` is only given by
        the seed command.
        """
        require_role(user, User.COORDINATOR)
        asset = Asset.objects.create(
            code=code or next_code(Asset, "A"),
            department=user.department,  # set on the server, never taken from the form
            created_by=user,
            state=Asset.DRAFT,
            **data,
        )
        AssetStateMachine.record(asset, user, "Registered")
        return asset

    @staticmethod
    @transaction.atomic
    def update_draft(user, asset, data):
        AssetService.require_owning_coordinator(user, asset)
        if asset.state != Asset.DRAFT:
            raise BusinessRuleError("Only draft assets can be edited.")
        for field, value in data.items():
            setattr(asset, field, value)
        asset.save()
        AssetStateMachine.record(asset, user, "Edited", old_state=Asset.DRAFT)
        return asset

    # --- C3: publish, withdraw and search -------------------------------------

    @staticmethod
    @transaction.atomic
    def publish(user, asset):
        AssetService.require_owning_coordinator(user, asset)
        asset.available_quantity = asset.quantity
        AssetStateMachine.change_state(asset, Asset.AVAILABLE, user, "Published")

    @staticmethod
    @transaction.atomic
    def withdraw(user, asset):
        from resource_requests.models import Request  # imported here to avoid a circular import

        AssetService.require_owning_coordinator(user, asset)
        if asset.requests.filter(state__in=[Request.SUBMITTED, Request.RELEASED]).exists():
            raise BusinessRuleError("This asset has open requests. Decline them before withdrawing it.")
        asset.available_quantity = 0
        AssetStateMachine.change_state(asset, Asset.WITHDRAWN, user, "Withdrawn")

    @staticmethod
    def search(keyword="", category=None, condition="", department=None):
        """Published assets with free units, filtered by the search form."""
        assets = Asset.objects.filter(state=Asset.AVAILABLE, available_quantity__gt=0)
        if keyword:
            assets = assets.filter(
                Q(name__icontains=keyword) | Q(description__icontains=keyword)
                | Q(tags__icontains=keyword) | Q(code__icontains=keyword)
            )
        if category:
            assets = assets.filter(category=category)
        if condition:
            assets = assets.filter(condition=condition)
        if department:
            assets = assets.filter(department=department)
        return assets.select_related("category", "department")

    # --- C5: reserve, hand over, complete --------------------------------------
    # These are called by ApprovalService and TransferService, which check
    # the user's permissions first.

    @staticmethod
    @transaction.atomic
    def reserve_units(asset, quantity, user, request_code):
        """Reserve units for an approved request and return the asset record that holds them.

        The UPDATE below only changes the row if enough units are still free at
        this moment. If two approvals race for the last unit, only one UPDATE
        succeeds; the other gets 0 rows and is refused (design FR-4.5, QUA-4).
        """
        updated_rows = Asset.objects.filter(
            pk=asset.pk, state=Asset.AVAILABLE, available_quantity__gte=quantity
        ).update(available_quantity=F("available_quantity") - quantity)

        asset.refresh_from_db()
        if updated_rows == 0:
            raise BusinessRuleError(
                f"Not enough units: {asset.code} has {asset.available_quantity} free "
                f"(state {asset.state}) but the request needs {quantity}."
            )

        if asset.available_quantity == 0:
            # No free units left: the whole record is now reserved.
            AssetStateMachine.change_state(asset, Asset.RESERVED, user, "Reserved", f"All units reserved for {request_code}")
            return asset

        # Only some units are taken: they get their own record, linked to this one (FR-4.15).
        asset.quantity -= quantity
        asset.save()
        part = Asset.objects.create(
            code=next_code(Asset, "A"),
            name=asset.name,
            description=asset.description,
            category=asset.category,
            condition=asset.condition,
            tags=asset.tags,
            department=asset.department,
            quantity=quantity,
            available_quantity=0,
            estimated_value=asset.estimated_value,
            weight_kg=asset.weight_kg,
            repair_cost=asset.repair_cost,
            state=Asset.AVAILABLE,
            parent=asset,
            created_by=user,
        )
        AssetStateMachine.record(asset, user, "Units split off", old_state=Asset.AVAILABLE,
                                 note=f"{quantity} units moved to {part.code} for {request_code}")
        AssetStateMachine.record(part, user, "Created from split", note=f"{quantity} units taken from {asset.code}")
        AssetStateMachine.change_state(part, Asset.RESERVED, user, "Reserved", f"Reserved for {request_code}")
        return part

    @staticmethod
    def release_reservation(asset, user, request_code):
        """Put reserved units back on offer (request cancelled after approval)."""
        asset.available_quantity = asset.quantity
        AssetStateMachine.change_state(asset, Asset.AVAILABLE, user, "Reservation released",
                                       f"{request_code} was cancelled")

    @staticmethod
    def hand_over(asset, user, request_code):
        AssetStateMachine.change_state(asset, Asset.IN_TRANSFER, user, "Handed over", f"For {request_code}")

    @staticmethod
    def complete_transfer(asset, user, to_department, condition, request_code):
        """Receipt confirmed: the receiving department becomes the owner (FR-4.11)."""
        old_department = asset.department
        asset.department = to_department
        asset.condition = condition
        AssetStateMachine.change_state(
            asset, Asset.IN_USE, user, "Received",
            f"{request_code}: owner changed from {old_department} to {to_department}, condition on arrival {condition}",
        )
