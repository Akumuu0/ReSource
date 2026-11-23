from django import forms

from accounts.models import Department
from resource_requests.models import Request

# HTML date inputs need the ISO format (YYYY-MM-DD) to show a value.
DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class PeriodForm(forms.Form):
    """Optional period and department, used by the dashboard."""

    date_from = forms.DateField(required=False, widget=DATE_INPUT, label="From")
    date_to = forms.DateField(required=False, widget=DATE_INPUT, label="To")
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False,
                                        empty_label="All departments", label="Department")


class ReportFilterForm(PeriodForm):
    """Filters of the request report (C9)."""

    state = forms.ChoiceField(choices=[("", "Any state")] + Request.STATE_CHOICES, required=False)


class SummaryForm(forms.Form):
    """Period for a generated summary (AI-5)."""

    period_start = forms.DateField(widget=DATE_INPUT, label="From")
    period_end = forms.DateField(widget=DATE_INPUT, label="To")

    def clean(self):
        data = super().clean()
        if data.get("period_start") and data.get("period_end") and data["period_start"] > data["period_end"]:
            raise forms.ValidationError("The start date must be before the end date.")
        return data
