"""Pages for requests, approvals and transfers.

Naming: `request` is the web request (Django's name); `req` is one of our Request records.
Views stay thin: they read the form, call a service, and show the result.
The services do all the permission and state checks.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.common import BusinessRuleError
from accounts.models import User
from accounts.permissions import role_required
from ai.models import FACTOR_LABELS, AIOutput, Recommendation
from ai.ranking import FORMULAS, RULES_VERSION, WEAK_SCORE, WEIGHTS, RankingModel
from assets.models import Asset
from assets.services import AssetService

from .forms import NeedForm, ReceiptForm, RequestForm
from .models import Request
from .services import ApprovalService, RequestService, TransferService


def run_action(request, req, action, success_message):
    """Run one service call for a button, show success or the rule that was broken."""
    try:
        action()
        messages.success(request, success_message)
    except BusinessRuleError as error:
        messages.error(request, str(error))
    return redirect("request_detail", pk=req.pk)


# --- C4: submit and track -------------------------------------------------------

@role_required(User.REPRESENTATIVE)
def request_create(request, asset_pk):
    asset = get_object_or_404(Asset, pk=asset_pk)
    # "Request this" on the need page passes what was already typed.
    initial = {"quantity": request.GET.get("quantity", 1), "purpose": request.GET.get("purpose", ""),
               "needed_by": request.GET.get("needed_by")}
    form = RequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            req = RequestService.submit(request.user, asset, **form.cleaned_data)
        except BusinessRuleError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Request {req.code} submitted. The Asset Coordinator of {asset.department} has been notified.")
            return redirect("request_detail", pk=req.pk)
    return render(request, "resource_requests/request_form.html", {"form": form, "asset": asset})


@role_required(User.REPRESENTATIVE)
def my_requests(request):
    return render(request, "resource_requests/my_requests.html", {"requests": RequestService.my_requests(request.user)})


@login_required
def tasks(request):
    return render(request, "resource_requests/tasks.html", {"sections": RequestService.tasks_for(request.user)})


@login_required
def request_detail(request, pk):
    req = get_object_or_404(Request.objects.select_related(
        "asset__department", "department", "requester", "recommendation__output"), pk=pk)
    if not req.is_visible_to(request.user):
        raise PermissionDenied("This request belongs to other departments.")
    user = request.user
    transfer = req.get_transfer()
    approvals = list(req.approvals.select_related("decided_by"))
    recommendation = req.recommendation
    context = {
        "req": req,
        "transfer": transfer,
        "approvals": approvals,
        "history": request_history(req, approvals, transfer),
        "recommendation": recommendation,
        "candidates": recommendation.output.recommendations.count() if recommendation else 0,
        # FR-4.4: shown to the approver; the service checks it again.
        "involved": req.requester_id == user.id or any(approval.is_by(user) for approval in approvals),
        "receipt_form": ReceiptForm(),
        # Which buttons to show. The services check everything again on the server.
        "can_release": req.state == Request.SUBMITTED and AssetService.is_owning_coordinator(user, req.asset),
        "can_approve": req.state == Request.RELEASED and user.is_administrator,
        "can_hand_over": req.state == Request.APPROVED and AssetService.is_owning_coordinator(user, transfer.asset),
        "can_confirm": (req.state == Request.IN_TRANSFER and user.department_id == req.department_id
                        and not user.is_administrator),
        "can_cancel": req.requester_id == user.id and req.state in (
            Request.OPEN, Request.SUBMITTED, Request.RELEASED, Request.APPROVED),
        "can_choose_match": req.requester_id == user.id and req.state == Request.OPEN,
    }
    return render(request, "resource_requests/request_detail.html", context)


def request_history(req, approvals, transfer):
    """Who did what and when, oldest first, for the History card."""
    history = [(req.created_at, f"Request made by {req.requester.display_name()} ({req.department})")]
    if req.recommendation and req.recommendation.output.decided_at:
        history.append((req.recommendation.output.decided_at, "Match chosen from the AI recommendations"))
    verbs = {("Release", "Approved"): "Released", ("Release", "Rejected"): "Declined",
             ("Approval", "Approved"): "Approved", ("Approval", "Rejected"): "Rejected"}
    for approval in approvals:
        text = f"{verbs[(approval.step, approval.decision)]} by {approval.decided_by.display_name()}"
        history.append((approval.decided_at, text + (f": {approval.reason}" if approval.reason else "")))
    if transfer and transfer.handed_over_at:
        history.append((transfer.handed_over_at, f"Handed over by {transfer.handed_over_by.display_name()}"))
    if transfer and transfer.received_at:
        history.append((transfer.received_at, f"Received by {transfer.received_by.display_name()}, "
                                              f"condition {transfer.condition_on_arrival}"))
    return sorted(history, key=lambda item: item[0])


# --- C5: buttons on the request page ----------------------------------------------

@require_POST
@login_required
def release(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req, lambda: ApprovalService.release(request.user, req),
                      f"{req.code} released. Administrators have been notified.")


@require_POST
@login_required
def decline(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req, lambda: ApprovalService.decline(request.user, req, request.POST.get("reason")),
                      f"{req.code} declined.")


@require_POST
@login_required
def approve(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req, lambda: ApprovalService.approve(request.user, req),
                      f"{req.code} approved and {req.quantity} units reserved.")


@require_POST
@login_required
def reject(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req, lambda: ApprovalService.reject(request.user, req, request.POST.get("reason")),
                      f"{req.code} rejected.")


@require_POST
@login_required
def hand_over(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req, lambda: TransferService.hand_over(request.user, req),
                      f"{req.code} handed over. The requester has been asked to confirm receipt.")


@require_POST
@login_required
def confirm_receipt(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req,
                      lambda: TransferService.confirm_receipt(request.user, req, request.POST.get("condition")),
                      f"Receipt of {req.code} confirmed. The asset now belongs to {req.department}.")


@require_POST
@login_required
def cancel(request, pk):
    req = get_object_or_404(Request, pk=pk)
    return run_action(request, req, lambda: RequestService.cancel(request.user, req, request.POST.get("reason")),
                      f"{req.code} cancelled.")


# --- AI-2: describe a need, see the top 5 matches, choose one or reject all --------

def score_rows():
    """The eight factors with their weights and formulas, for "How the score works"."""
    return [(FACTOR_LABELS[key], WEIGHTS[key], FORMULAS[key]) for key in WEIGHTS]


@role_required(User.REPRESENTATIVE)
def need_create(request):
    """Design mockup 7.2: describe the need, check the listings that may meet it, then submit it.

    Two buttons (the "action" field):
      check  - rank the published assets for this need without saving it (AI-2)
      submit - save the need as an open request and go to its matches
    """
    form = NeedForm(request.POST or None, initial={"quantity": 1})
    listings, output = [], None
    if request.method == "POST" and form.is_valid():
        if request.POST.get("action") == "check":
            draft = Request(requester=request.user, department=request.user.department, **form.cleaned_data)
            listings, output = RankingModel().rank(request.user, draft)  # nothing is saved for the need
        else:
            try:
                req = RequestService.submit_need(request.user, **form.cleaned_data)
            except BusinessRuleError as error:
                messages.error(request, str(error))
            else:
                return redirect("request_matches", pk=req.pk)
    context = {"form": form, "listings": listings, "output": output,
               "checked": request.POST.get("action") == "check" and form.is_valid()}
    return render(request, "resource_requests/need_form.html", context)


@login_required
def matches(request, pk):
    """Design mockup 7.3: the ranked matches with factors, confidence and reason."""
    req = get_object_or_404(Request, pk=pk)
    RequestService.require_requester(request.user, req)
    if req.state != Request.OPEN:
        messages.info(request, f"{req.code} is {req.state}; matches are shown only for open needs.")
        return redirect("request_detail", pk=pk)
    recommendations, output = RankingModel().rank(request.user, req)
    context = {
        "req": req,
        "top": recommendations[0] if recommendations else None,
        "others": recommendations[1:],
        "output": output,
        "score_rows": score_rows(),
        "rules_version": RULES_VERSION,
        "weak": bool(recommendations) and recommendations[0].score < WEAK_SCORE,
    }
    return render(request, "resource_requests/matches.html", context)


def matching_output(request):
    """The AIOutput row of the match list the user is answering (only their own)."""
    return AIOutput.objects.filter(
        pk=request.POST.get("ai_output_id") or None, requested_by=request.user, feature=AIOutput.MATCHING
    ).first()


@require_POST
@login_required
def choose_match(request, pk, rec_pk):
    req = get_object_or_404(Request, pk=pk)
    # Only a recommendation that was shown to this user.
    rec = get_object_or_404(Recommendation.objects.select_related("asset", "output"),
                            pk=rec_pk, output__requested_by=request.user)
    reason = request.POST.get("reason", "").strip()
    try:
        RequestService.choose_match(request.user, req, rec.asset, recommendation=rec, reason=reason)
    except BusinessRuleError as error:
        messages.error(request, str(error))
        return redirect("request_matches", pk=pk)
    if rec.rank == 1:
        decision = f"Selected the top match: {rec.asset.code}"
    else:
        decision = f"Chose match {rec.rank} ({rec.asset.code}) instead of match 1: {reason}"
    rec.output.record_decision(request.user, decision)
    messages.success(request, f"{req.code} now asks for {rec.asset.code}. "
                              f"The Asset Coordinator of {rec.asset.department} has been notified.")
    return redirect("request_detail", pk=pk)


@require_POST
@login_required
def reject_matches(request, pk):
    req = get_object_or_404(Request, pk=pk)
    reason = request.POST.get("reason", "")
    try:
        RequestService.reject_matches(request.user, req, reason)
    except BusinessRuleError as error:
        messages.error(request, str(error))
        return redirect("request_matches", pk=pk)
    output = matching_output(request)
    if output:
        output.record_decision(request.user, f"Rejected all matches: {reason}")
    messages.success(request, f"{req.code} closed: no suitable match.")
    return redirect("request_detail", pk=pk)
