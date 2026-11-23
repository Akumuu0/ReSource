"""Pages: sustainability dashboard (C7) and request report with CSV (C9)."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from .forms import PeriodForm, ReportFilterForm
from .services import MEASURES, RequestReportService, SustainabilityCalculator


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
