"""Pages for assets: search, my department's assets, details, register and edit."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.common import BusinessRuleError
from accounts.models import User
from accounts.permissions import role_required

from .forms import AssetForm, SearchForm
from .models import Asset
from .services import AssetService


@login_required
def asset_list(request):
    """C3: search published assets."""
    form = SearchForm(request.GET or None)
    filters = form.cleaned_data if form.is_valid() else {}
    assets = AssetService.search(
        keyword=filters.get("q", ""),
        category=filters.get("category"),
        condition=filters.get("condition", ""),
        department=filters.get("department"),
    )
    return render(request, "assets/asset_list.html", {"form": form, "assets": assets})


@role_required(User.COORDINATOR)
def my_assets(request):
    assets = Asset.objects.filter(department=request.user.department).select_related("category")
    return render(request, "assets/my_assets.html", {"assets": assets})


@login_required
def asset_detail(request, pk):
    asset = get_object_or_404(Asset.objects.select_related("category", "department", "parent"), pk=pk)
    user = request.user
    if not asset.is_visible_to(user):
        raise PermissionDenied("Draft assets are visible only to their own department.")
    is_owner = AssetService.is_owning_coordinator(user, asset)
    context = {
        "asset": asset,
        "events": asset.events.select_related("performed_by"),
        "parts": asset.parts.all(),
        # Buttons to show; the services check again on the server.
        "can_edit": is_owner and asset.state == Asset.DRAFT,
        "can_publish": is_owner and asset.state == Asset.DRAFT,
        "can_withdraw": is_owner and asset.state == Asset.AVAILABLE,
        # Not for the owner's own department: the transfer would change nothing (C5).
        "can_request": (user.is_representative and asset.state == Asset.AVAILABLE and asset.available_quantity > 0
                        and asset.department_id != user.department_id),
    }
    return render(request, "assets/asset_detail.html", context)


@role_required(User.COORDINATOR)
def asset_form(request, pk=None):
    """C2: register a new asset (pk is None) or edit a draft (design mockup 7.1)."""
    asset = get_object_or_404(Asset, pk=pk) if pk else None
    if asset:
        AssetService.require_owning_coordinator(request.user, asset)
    form = AssetForm(request.POST or None, instance=asset)
    if request.method == "POST" and form.is_valid():
        try:
            if asset:
                asset = AssetService.update_draft(request.user, asset, form.cleaned_data)
            else:
                asset = AssetService.register(request.user, form.cleaned_data)
        except BusinessRuleError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"{asset.code} saved as {asset.state}.")
            return redirect("asset_detail", pk=asset.pk)
    return render(request, "assets/asset_form.html", {"form": form, "asset": asset})


@require_POST
@login_required
def publish(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    try:
        AssetService.publish(request.user, asset)
        messages.success(request, f"{asset.code} is now published and can be requested.")
    except BusinessRuleError as error:
        messages.error(request, str(error))
    return redirect("asset_detail", pk=pk)


@require_POST
@login_required
def withdraw(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    try:
        AssetService.withdraw(request.user, asset)
        messages.success(request, f"{asset.code} has been withdrawn.")
    except BusinessRuleError as error:
        messages.error(request, str(error))
    return redirect("asset_detail", pk=pk)
