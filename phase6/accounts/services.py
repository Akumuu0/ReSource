"""Notification service (design: Notify interface, FR-7.N)."""
from django.utils import timezone

from .models import Notification, User


class NotificationService:

    @staticmethod
    def notify(users, event_type, message, link=""):
        """Save one in-app message for each user in the list."""
        for user in users:
            Notification.objects.create(recipient=user, event_type=event_type, message=message, link=link)

    @staticmethod
    def unread_count(user):
        return user.notifications.filter(read_at__isnull=True).count()

    @staticmethod
    def mark_all_read(user):
        user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())

    # --- who should be told -------------------------------------------------

    @staticmethod
    def coordinators_of(department):
        return list(User.objects.filter(role=User.COORDINATOR, department=department, is_active=True))

    @staticmethod
    def administrators():
        return list(User.objects.filter(role=User.ADMINISTRATOR, is_active=True))
