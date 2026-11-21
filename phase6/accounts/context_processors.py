"""Adds the unread notification count to every page, for the header badge (C8)."""
from .services import NotificationService


def notifications(request):
    if request.user.is_authenticated:
        return {"unread_count": NotificationService.unread_count(request.user)}
    return {"unread_count": 0}
