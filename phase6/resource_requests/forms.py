from django import forms

# HTML date inputs need the ISO format (YYYY-MM-DD) to show a value.
DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class RequestForm(forms.Form):
    """Request a listed asset (C4)."""

    quantity = forms.IntegerField(min_value=1)
    purpose = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    needed_by = forms.DateField(widget=DATE_INPUT, label="Needed by")
