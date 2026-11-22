from django import forms

from accounts.models import Department

# HTML date inputs need the ISO format (YYYY-MM-DD) to show a value.
DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class PeriodForm(forms.Form):
    """Optional period and department, used by the dashboard."""

    date_from = forms.DateField(required=False, widget=DATE_INPUT, label="From")
    date_to = forms.DateField(required=False, widget=DATE_INPUT, label="To")
    department = forms.ModelChoiceField(queryset=Department.objects.all(), required=False,
                                        empty_label="All departments", label="Department")
