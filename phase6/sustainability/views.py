"""Pages: sustainability dashboard (C7)."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .forms import PeriodForm
from .services import MEASURES, SustainabilityCalculator


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
