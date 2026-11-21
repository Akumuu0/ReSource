"""Asset business rules (design: Assets and Catalogue module, Table 16-1).

Views never change assets directly; they call these methods.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q

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
