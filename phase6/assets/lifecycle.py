"""The asset state machine (design Fig. 12-1, subset for the draft).

This is the ONLY place that changes Asset.state. Any move that is not in
ALLOWED_MOVES is refused, and every change writes a LifecycleEvent.
"""
from accounts.common import BusinessRuleError

from .models import Asset, LifecycleEvent


class AssetStateMachine:

    ALLOWED_MOVES = {
        (Asset.DRAFT, Asset.AVAILABLE),        # publish
        (Asset.AVAILABLE, Asset.RESERVED),     # final approval reserves the units
        (Asset.RESERVED, Asset.IN_TRANSFER),   # hand over
        (Asset.IN_TRANSFER, Asset.IN_USE),     # receipt confirmed
        (Asset.RESERVED, Asset.AVAILABLE),     # request cancelled after approval
        (Asset.AVAILABLE, Asset.WITHDRAWN),    # withdraw
    }

    @classmethod
    def can_move(cls, old_state, new_state):
        return (old_state, new_state) in cls.ALLOWED_MOVES

    @classmethod
    def change_state(cls, asset, new_state, user, action, note=""):
        """Move the asset to new_state, or raise BusinessRuleError if the move is not allowed."""
        old_state = asset.state
        if not cls.can_move(old_state, new_state):
            raise BusinessRuleError(f"An asset cannot move from {old_state} to {new_state}.")
        asset.state = new_state
        asset.save()
        cls.record(asset, user, action, old_state=old_state, note=note)

    @staticmethod
    def record(asset, user, action, old_state="", note=""):
        """Write one history line. Also used for events without a state change."""
        LifecycleEvent.objects.create(
            asset=asset,
            action=action,
            old_state=old_state,
            new_state=asset.state,
            performed_by=user,
            note=note,
        )
