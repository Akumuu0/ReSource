"""Home page and notifications."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .services import NotificationService


@login_required
def home(request):
    """Who am I: name, role and department."""
    return render(request, "accounts/home.html")


@login_required
def notifications(request):
    """C8: the user's in-app messages, newest first."""
    return render(request, "accounts/notifications.html", {"notifications": request.user.notifications.all()[:100]})


@require_POST
@login_required
def mark_all_read(request):
    NotificationService.mark_all_read(request.user)
    return redirect("notifications")
