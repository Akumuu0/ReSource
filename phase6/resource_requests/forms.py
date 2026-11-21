from django import forms

from assets.models import Asset

# HTML date inputs need the ISO format (YYYY-MM-DD) to show a value.
DATE_INPUT = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


class RequestForm(forms.Form):
    """Request a listed asset (C4)."""

    quantity = forms.IntegerField(min_value=1)
    purpose = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    needed_by = forms.DateField(widget=DATE_INPUT, label="Needed by")


class ReasonForm(forms.Form):
    """A reason, required to decline, reject or reject all matches."""

    reason = forms.CharField(max_length=255)


class ReceiptForm(forms.Form):
    """Confirm receipt with the condition on arrival (FR-4.10)."""

    condition = forms.ChoiceField(choices=Asset.CONDITION_CHOICES, label="Condition on arrival")
