"""Pages for assets: search, my department's assets, details, register and edit."""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.common import BusinessRuleError
from accounts.models import User
from accounts.permissions import role_required
from ai.classification import FIELDS, ClassificationService
from ai.models import AIOutput

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


def field_set(text):
    """ "category,tags" -> {"category", "tags"}, keeping only the fields the AI suggests."""
    return {field for field in text.split(",") if field in FIELDS}


@role_required(User.COORDINATOR)
def asset_form(request, pk=None):
    """C2: register a new asset (pk is None) or edit a draft (design mockup 7.1).

    The buttons send an "action":
      suggest          - ask ClassificationService (AI-1) for category, condition and tags
      accept:<field>   - copy one suggested value into the form ("accept:all" for all three)
      reject:<field>   - mark one suggestion as rejected; the field keeps what was typed
      save             - validate and save the draft
    Nothing is saved until "save". Accepted and rejected fields travel in two hidden inputs.
    """
    asset = get_object_or_404(Asset, pk=pk) if pk else None
    if asset:
        AssetService.require_owning_coordinator(request.user, asset)
    action = request.POST.get("action", "save")
    accepted = field_set(request.POST.get("accepted", ""))
    rejected = field_set(request.POST.get("rejected", ""))
    suggestion = None  # the AIOutput being shown, if any
    if request.method == "POST":
        suggestion = AIOutput.objects.filter(
            pk=request.POST.get("ai_output_id") or None, requested_by=request.user, feature=AIOutput.CLASSIFICATION
        ).first()

    if request.method == "POST" and action == "suggest":
        name, description = request.POST.get("name", ""), request.POST.get("description", "")
        if name.strip() or description.strip():
            suggestion = ClassificationService().suggest(request.user, name, description).output
            accepted, rejected = set(), set()
        else:
            messages.warning(request, "Type a name and a description first.")
        form = AssetForm(initial=request.POST.dict(), instance=asset)  # keep what was typed, not saved

    elif request.method == "POST" and action.startswith("accept:") and suggestion:
        fields = set(FIELDS) if action == "accept:all" else field_set(action.split(":")[1])
        values = request.POST.dict()
        values.update(ClassificationService.form_values(suggestion, fields))
        accepted, rejected = accepted | fields, rejected - fields
        form = AssetForm(initial=values, instance=asset)

    elif request.method == "POST" and action.startswith("reject:") and suggestion:
        fields = field_set(action.split(":")[1])
        accepted, rejected = accepted - fields, rejected | fields
        form = AssetForm(initial=request.POST.dict(), instance=asset)

    else:
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
                if suggestion:  # record the human decision on the AI suggestion (H-1)
                    suggestion.record_decision(
                        request.user, ClassificationService.describe_decision(suggestion, form.cleaned_data, rejected))
                messages.success(request, f"{asset.code} saved as {asset.state}.")
                return redirect("asset_detail", pk=asset.pk)

    data = json.loads(suggestion.output_text) if suggestion else None
    context = {
        "form": form,
        "asset": asset,
        "suggestion_output": suggestion,
        "suggestion": data,
        "rows": ClassificationService.rows(data, accepted, rejected) if data else [],
        "accepted": ",".join(sorted(accepted)),
        "rejected": ",".join(sorted(rejected)),
    }
    return render(request, "assets/asset_form.html", context)


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
