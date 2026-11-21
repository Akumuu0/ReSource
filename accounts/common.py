"""Small helpers shared by every app."""
from django.utils import timezone


class BusinessRuleError(Exception):
    """A business rule was broken (for example "not enough units").

    Services raise it; views catch it and show the message to the user.
    Permission problems use Django's PermissionDenied instead (HTTP 403).
    """


def next_code(model, prefix):
    """Return the next readable code, e.g. "A-2026-0413" or "R-2026-0392".

    The number is one more than the highest code of this year.
    """
    start = f"{prefix}-{timezone.now().year}-"
    last = model.objects.filter(code__startswith=start).order_by("-code").first()
    number = int(last.code.split("-")[2]) + 1 if last else 1
    return f"{start}{number:04d}"
