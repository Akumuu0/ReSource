"""Pages: sustainability dashboard (C7), request report with CSV (C9), AI summaries (AI-5)."""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.common import BusinessRuleError
from accounts.models import User
from accounts.permissions import role_required
from ai.report_generator import ReportGenerator

from .forms import PeriodForm, ReportFilterForm, SummaryForm
from .models import AIReport
from .services import MEASURES, RequestReportService, SummaryService, SustainabilityCalculator


@login_required
def dashboard(request):
    form = PeriodForm(request.GET or None)
    filters = form.cleaned_data if form.is_valid() else {}
    calculator = SustainabilityCalculator(filters.get("date_from"), filters.get("date_to"), filters.get("department"))
    totals, rows = calculator.calculate()
    shown = calculator.display(totals)
    measures = [dict(measure, value=shown[measure["key"]]) for measure in MEASURES]
    context = {
        "form": form,
        "measures": measures,
        "rows": rows,
        "missing": [row for row in rows if row["co2e"] is None],  # left out of CO2e (FR-13.8)
        "trend": calculator.monthly_items(),
        "latest_summary": AIReport.objects.filter(state=AIReport.PUBLISHED).order_by("-published_at").first(),
    }
    return render(request, "sustainability/dashboard.html", context)


@login_required
def report_table(request):
    form = ReportFilterForm(request.GET or None)
    filters = form.cleaned_data if form.is_valid() else {}
    requests = RequestReportService.requests_for(
        request.user,
        state=filters.get("state", ""),
        department=filters.get("department"),
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
    )
    if request.GET.get("export") == "csv":
        response = HttpResponse(RequestReportService.to_csv(requests), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="resource-requests.csv"'
        return response
    context = {
        "form": form,
        "columns": RequestReportService.COLUMNS,
        "rows": [RequestReportService.as_row(req) for req in requests],
        "csv_query": request.GET.urlencode(),
    }
    return render(request, "sustainability/report_table.html", context)


# --- AI-5: generated summaries ------------------------------------------------------

@login_required
def summary_list(request):
    """Administrators see every summary (drafts included); other users only see published ones."""
    if request.user.is_administrator:
        reports = AIReport.objects.all()
    else:
        reports = AIReport.objects.filter(state=AIReport.PUBLISHED)
    today = date.today()
    form = SummaryForm(initial={"period_start": today.replace(day=1), "period_end": today})
    return render(request, "sustainability/summary_list.html", {"reports": reports, "form": form})


@require_POST
@role_required(User.ADMINISTRATOR)
def summary_create(request):
    """Generate a new draft summary for the chosen period, then open it for review."""
    form = SummaryForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please choose a valid period.")
        return redirect("summary_list")
    report = ReportGenerator().generate(request.user, form.cleaned_data["period_start"], form.cleaned_data["period_end"])
    messages.success(request, "Draft summary created. Review and edit it, then publish it.")
    return redirect("summary_detail", pk=report.pk)


@login_required
def summary_detail(request, pk):
    report = get_object_or_404(AIReport, pk=pk)
    if report.state != AIReport.PUBLISHED and not request.user.is_administrator:
        raise PermissionDenied("Only published summaries can be read by everyone.")
    if request.method == "POST":
        try:
            if request.POST.get("action") == "publish":
                SummaryService.publish(request.user, report, request.POST.get("final_text"))
                messages.success(request, "Summary published.")
            else:
                SummaryService.discard(request.user, report)
                messages.success(request, "Summary discarded.")
        except BusinessRuleError as error:
            messages.error(request, str(error))
        return redirect("summary_detail", pk=pk)
    pieces = ReportGenerator.mark_numbers(report.draft_text, report)
    numbers = [piece for piece in pieces if piece["number"]]
    context = {
        "report": report,
        "figures": report.figures.all(),
        "output": report.ai_output,
        "pieces": pieces,
        "numbers_checked": sum(1 for piece in numbers if piece["checked"]),
        "numbers_total": len(numbers),
    }
    return render(request, "sustainability/summary_detail.html", context)
