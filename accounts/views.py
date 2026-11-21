"""Home page."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Who am I: name, role and department."""
    return render(request, "accounts/home.html")
